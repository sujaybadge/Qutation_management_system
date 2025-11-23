import uuid
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import json

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required

from quotation_models.models import (
    Buyer,
    CatalogItem,
    Company,
    Instruction,
    Quotation,
    QuotationItem,
    TemplateStyle,
    SellerQuote,
)
from .forms import (
    BuyerForm,
    CompanyForm,
    QuotationForm,
    QuotationBlockForm,
    PlainItemFormSet,
    get_item_formset,
)

TAX_RATE = Decimal("0.18")


def _generate_code() -> str:
    """Replicate the desktop app's compact code style."""
    return dt.datetime.now().strftime("Q%y%m%d-") + uuid.uuid4().hex[:6].upper()


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _generate_seller_code() -> str:
    return "SQ" + dt.datetime.now().strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6].upper()


def _unique_seller_code() -> str:
    code = _generate_seller_code()
    while SellerQuote.objects.filter(seller_code=code).exists():
        code = _generate_seller_code()
    return code


def home(request):
    return redirect("quotations:list")


@login_required
def quotation_list(request):
    qs = Quotation.objects.filter(created_by=request.user).select_related("buyer").prefetch_related("items").order_by("-created_at")
    q = request.GET.get("q", "").strip()
    buyer_id = request.GET.get("buyer", "").strip()
    date_from = request.GET.get("from", "").strip()
    date_to = request.GET.get("to", "").strip()

    if q:
        qs = qs.filter(code__icontains=q) | qs.filter(buyer__name__icontains=q)
    if buyer_id:
        qs = qs.filter(buyer_id=buyer_id)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    buyers = Buyer.objects.order_by("name")
    quotes = qs
    return render(
        request,
        "quotations/quotation_list.html",
        {
            "quotes": quotes,
            "buyers": buyers,
            "q": q,
            "buyer_id": buyer_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@login_required
def quotation_create(request):
    return _handle_quotation_form(request, mode="create")


@login_required
def quotation_copy(request, pk: int):
    source = get_object_or_404(Quotation.objects.prefetch_related("items"), pk=pk)
    return _handle_quotation_form(request, mode="copy", source=source)


@login_required
def quotation_multi_create(request):
    initial_blocks = int(request.GET.get("count", "1") or 1)
    copy_param = (request.GET.get("copy") or request.GET.get("copy_code") or "").strip()
    copy_source = None
    initial_items = None
    block_initial = None
    copy_error = None
    if copy_param:
        try:
            copy_source = Quotation.objects.filter(code__iexact=copy_param).prefetch_related("items").first()
            if not copy_source and copy_param.isdigit():
                copy_source = Quotation.objects.filter(pk=int(copy_param)).prefetch_related("items").first()
        except Exception:
            copy_source = None
        if copy_source:
            initial_items = [
                {
                    "item_name": it.item_name,
                    "description": it.description,
                    "qty": it.qty,
                    "rate": it.rate,
                }
                for it in copy_source.items.all()
            ]
            block_initial = [
                {
                    "buyer": copy_source.buyer_id,
                    "notes": copy_source.notes,
                    "currency": copy_source.currency,
                    "valid_until": copy_source.valid_until.date() if copy_source.valid_until else None,
                }
                for _ in range(initial_blocks)
            ]
        else:
            copy_error = f"No quotation found for code/id '{copy_param}'."

    BlockFormSet = forms.formset_factory(QuotationBlockForm, extra=initial_blocks, can_delete=True, validate_min=True, min_num=1)
    if request.method == "POST":
        block_formset = BlockFormSet(request.POST, prefix="blocks")
    else:
        block_formset = BlockFormSet(prefix="blocks", initial=block_initial)

    item_formsets = []
    total_blocks = int(request.POST.get("blocks-TOTAL_FORMS", block_formset.total_form_count()))
    for i in range(total_blocks):
        if request.method == "POST":
            item_formsets.append(PlainItemFormSet(request.POST or None, prefix=f"items-{i}"))
        else:
            if initial_items:
                dyn_cls = forms.formset_factory(
                    PlainItemFormSet.form,
                    extra=max(len(initial_items), 1),
                    can_delete=True,
                    validate_min=False,
                    min_num=0,
                )
                item_formsets.append(dyn_cls(prefix=f"items-{i}", initial=initial_items))
            else:
                item_formsets.append(PlainItemFormSet(prefix=f"items-{i}"))

    if request.method == "POST" and block_formset.is_valid() and all(fs.is_valid() for fs in item_formsets):
        created = 0
        with transaction.atomic():
            for idx, bf in enumerate(block_formset.forms):
                if not bf.cleaned_data or bf.cleaned_data.get("DELETE"):
                    continue
                items_fs = item_formsets[idx]
                items_payload = []
                for form in items_fs.forms:
                    if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                        continue
                    name = (form.cleaned_data.get("item_name") or "").strip()
                    desc = (form.cleaned_data.get("description") or "").strip()
                    qty = Decimal(form.cleaned_data.get("qty") or 0)
                    rate = Decimal(form.cleaned_data.get("rate") or 0)
                    if not name and not desc and qty <= 0:
                        continue
                    amount = _money(qty * rate)
                    items_payload.append({"name": name, "desc": desc, "qty": qty, "rate": rate, "amount": amount})
                if not items_payload:
                    bf.add_error(None, "At least one item is required for this quote.")
                    continue

                q = Quotation.objects.create(
                    code=_generate_code(),
                    buyer=bf.cleaned_data["buyer"],
                    created_by=request.user,
                    notes=bf.cleaned_data.get("notes", ""),
                    currency=bf.cleaned_data.get("currency") or "INR",
                    valid_until=bf.cleaned_data.get("valid_until"),
                )
                subtotal = Decimal("0.00")
                for it in items_payload:
                    QuotationItem.objects.create(
                        quotation=q,
                        item_name=it["name"],
                        description=it["desc"],
                        qty=it["qty"],
                        rate=it["rate"],
                        amount=it["amount"],
                    )
                    subtotal += it["amount"]

                q.subtotal = _money(subtotal)
                q.tax = _money(subtotal * TAX_RATE)
                q.total = _money(q.subtotal + q.tax)
                q.save()

                tmpl = bf.cleaned_data.get("template")
                seller = bf.cleaned_data.get("seller")
                if seller and tmpl:
                    SellerQuote.objects.create(
                        quotation=q,
                        seller=seller,
                        template=tmpl,
                        seller_code=_unique_seller_code(),
                    )

                created += 1

        if created and not block_formset.non_form_errors():
            messages.success(request, f"Created {created} quotation(s).")
            return redirect(reverse("quotations:list"))

    block_items = list(zip(block_formset.forms, item_formsets, range(len(item_formsets))))
    context = {
        "block_formset": block_formset,
        "block_items": block_items,
        "item_formsets": item_formsets,
        "instruction_suggestions": list(Instruction.objects.all().order_by("text").values_list("text", flat=True)),
        "catalog_items": list(CatalogItem.objects.all().order_by("name").values_list("name", flat=True)),
        "catalog_map_json": json.dumps({ci.name: ci.description for ci in CatalogItem.objects.all()}, ensure_ascii=False),
        "copy_source": copy_source,
        "copy_error": copy_error,
    }
    return render(request, "quotations/quotation_multi_form.html", context)


@login_required
def quotation_edit(request, pk: int):
    quote = get_object_or_404(Quotation.objects.prefetch_related("items"), pk=pk)
    return _handle_quotation_form(request, instance=quote, mode="edit")


def _handle_quotation_form(request, mode: str, instance: Quotation | None = None, source: Quotation | None = None):
    is_edit = mode == "edit"
    initial = {}
    initial_items = []
    extra_rows = 2
    if source:
        initial = {
            "buyer": source.buyer,
            "notes": source.notes,
            "currency": source.currency,
            "valid_until": source.valid_until,
        }
        initial_items = [
            {"item_name": it.item_name, "description": it.description, "qty": it.qty, "rate": it.rate}
            for it in source.items.all()
        ]
        extra_rows = 1
    if is_edit:
        extra_rows = 1

    if not initial:
        initial = {"currency": "INR"}
    else:
        initial.setdefault("currency", "INR")

    target_instance = instance if is_edit else Quotation()
    form = QuotationForm(request.POST or None, instance=target_instance if is_edit else None, initial=None if is_edit else initial)

    ItemFormSetClass = get_item_formset(extra=extra_rows)
    if is_edit:
        items_formset = ItemFormSetClass(request.POST or None, instance=target_instance, prefix="items")
    else:
        empty_qs = QuotationItem.objects.none()
        items_formset = ItemFormSetClass(
            request.POST or None,
            instance=target_instance,
            prefix="items",
            initial=initial_items or None,
            queryset=empty_qs,
        )

    formsets_valid = False
    if request.method == "POST":
        form_valid = form.is_valid()
        items_valid = items_formset.is_valid()
        formsets_valid = form_valid and items_valid

    if request.method == "POST" and formsets_valid:
        with transaction.atomic():
            quotation = form.save(commit=False)
            if not is_edit:
                quotation.code = _generate_code()
            quotation.created_by = request.user
            quotation.save()

            items_formset.instance = quotation
            
            # Save items and handle deletions
            items = items_formset.save(commit=False)
            
            if is_edit:
                for obj in items_formset.deleted_objects:
                    obj.delete()

            for item in items:
                item.amount = _money(Decimal(item.qty or 0) * Decimal(item.rate or 0))
                item.save()
                
                if item.item_name:
                    CatalogItem.objects.update_or_create(
                        name=item.item_name.strip(),
                        defaults={"description": item.description.strip() if item.description else ""},
                    )
                if item.description:
                    Instruction.objects.update_or_create(text=item.description.strip())

            # Save seller quotes and handle deletions

            # Recalculate totals from all items in the database
            quotation.refresh_from_db()
            subtotal = sum(item.amount for item in quotation.items.all())
            
            quotation.subtotal = _money(subtotal)
            quotation.tax = _money(subtotal * TAX_RATE)
            quotation.total = _money(quotation.subtotal + quotation.tax)
            quotation.save()

            messages.success(
                request,
                "Quotation {} successfully {}.".format(
                    quotation.code,
                    "updated" if is_edit else "created" if mode == "create" else "copied",
                ),
            )
            return redirect(reverse("quotations:list"))

    context = {
        "form": form,
        "items_formset": items_formset,
        "mode": mode,
        "quotation": instance if is_edit else source,
        "catalog_items": list(CatalogItem.objects.all().order_by("name").values_list("name", flat=True)),
        "catalog_map_json": json.dumps(
            {ci.name: ci.description for ci in CatalogItem.objects.all()},
            ensure_ascii=False,
        ),
        "instruction_suggestions": list(Instruction.objects.all().order_by("text").values_list("text", flat=True)),
    }
    return render(request, "quotations/quotation_form.html", context)


@login_required
def quotation_delete(request, pk: int):
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == "POST":
        code = quotation.code
        quotation.delete()
        messages.success(request, f"Quotation {code} deleted.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/quotation_confirm_delete.html", {"quotation": quotation})


@login_required
def company_create(request):
    form = CompanyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        messages.success(request, f"Company {company.name} added.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/company_form.html", {"form": form})


@login_required
def company_list(request):
    companies = Company.objects.order_by("-is_main", "name")
    return render(request, "quotations/company_list.html", {"companies": companies})


@login_required
def company_edit(request, pk: int):
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Company {company.name} updated.")
        return redirect(reverse("quotations:company_list"))
    return render(request, "quotations/company_form.html", {"form": form, "company": company})


@login_required
def company_delete(request, pk: int):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        name = company.name
        company.delete()
        messages.success(request, f"Company {name} deleted.")
        return redirect(reverse("quotations:company_list"))
    return render(request, "quotations/company_confirm_delete.html", {"company": company})


@login_required
def buyer_create(request):
    form = BuyerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        buyer = form.save()
        messages.success(request, f"Customer {buyer.name} added.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/buyer_form.html", {"form": form})


@login_required
def buyer_list(request):
    buyers = Buyer.objects.order_by("name")
    return render(request, "quotations/buyer_list.html", {"buyers": buyers})


@login_required
def buyer_edit(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    form = BuyerForm(request.POST or None, instance=buyer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Customer {buyer.name} updated.")
        return redirect(reverse("quotations:buyer_list"))
    return render(request, "quotations/buyer_form.html", {"form": form, "buyer": buyer})


@login_required
def buyer_delete(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    if request.method == "POST":
        name = buyer.name
        buyer.delete()
        messages.success(request, f"Customer {name} deleted.")
        return redirect(reverse("quotations:buyer_list"))
    return render(request, "quotations/buyer_confirm_delete.html", {"buyer": buyer})


@login_required
def buyer_quotes(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    quotes = Quotation.objects.filter(buyer=buyer, created_by=request.user).order_by("-created_at").prefetch_related("items")
    return render(request, "quotations/buyer_quotes.html", {"buyer": buyer, "quotes": quotes})
