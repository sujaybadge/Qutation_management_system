import uuid
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import json

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from quotation_models.models import Buyer, CatalogItem, Company, Instruction, Quotation, QuotationItem
from .forms import BuyerForm, CompanyForm, QuotationForm, get_item_formset

TAX_RATE = Decimal("0.18")


def _generate_code() -> str:
    """Replicate the desktop app's compact code style."""
    return dt.datetime.now().strftime("Q%y%m%d-") + uuid.uuid4().hex[:6].upper()


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def home(request):
    return redirect("quotations:list")


def quotation_list(request):
    qs = Quotation.objects.select_related("buyer").prefetch_related("items").order_by("-created_at")
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


def quotation_create(request):
    return _handle_quotation_form(request, mode="create")


def quotation_copy(request, pk: int):
    source = get_object_or_404(Quotation.objects.prefetch_related("items"), pk=pk)
    return _handle_quotation_form(request, mode="copy", source=source)


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

    FormSetClass = get_item_formset(extra=extra_rows)
    if is_edit:
        items_formset = FormSetClass(request.POST or None, instance=target_instance, prefix="items")
    else:
        empty_qs = QuotationItem.objects.none()
        items_formset = FormSetClass(
            request.POST or None,
            instance=target_instance,
            prefix="items",
            initial=initial_items or None,
            queryset=empty_qs,
        )

    if request.method == "POST" and form.is_valid() and items_formset.is_valid():
        with transaction.atomic():
            quotation = form.save(commit=False)
            if not is_edit:
                quotation.code = _generate_code()
            quotation.save()

            # tie formset to the saved parent and process saves/deletes
            items_formset.instance = quotation
            # delete marked objects
            for obj in items_formset.deleted_objects:
                obj.delete()

            subtotal = Decimal("0.00")
            items_to_save = items_formset.save(commit=False)
            for item in items_to_save:
                item.quotation = quotation
                item.amount = _money(Decimal(item.qty or 0) * Decimal(item.rate or 0))
                item.save()
                subtotal += item.amount

                if item.item_name:
                    CatalogItem.objects.update_or_create(
                        name=item.item_name.strip(),
                        defaults={"description": item.description.strip() if item.description else ""},
                    )
                if item.description:
                    Instruction.objects.update_or_create(text=item.description.strip())

            # ensure any objects not in formset save are removed
            for stale in items_formset.get_queryset().exclude(pk__in=[i.pk for i in items_to_save if i.pk]):
                if stale not in items_formset.deleted_objects:
                    stale.delete()

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


def quotation_delete(request, pk: int):
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == "POST":
        code = quotation.code
        quotation.delete()
        messages.success(request, f"Quotation {code} deleted.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/quotation_confirm_delete.html", {"quotation": quotation})


def company_create(request):
    form = CompanyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        messages.success(request, f"Company {company.name} added.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/company_form.html", {"form": form})


def company_list(request):
    companies = Company.objects.order_by("-is_main", "name")
    return render(request, "quotations/company_list.html", {"companies": companies})


def company_edit(request, pk: int):
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Company {company.name} updated.")
        return redirect(reverse("quotations:company_list"))
    return render(request, "quotations/company_form.html", {"form": form, "company": company})


def company_delete(request, pk: int):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        name = company.name
        company.delete()
        messages.success(request, f"Company {name} deleted.")
        return redirect(reverse("quotations:company_list"))
    return render(request, "quotations/company_confirm_delete.html", {"company": company})


def buyer_create(request):
    form = BuyerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        buyer = form.save()
        messages.success(request, f"Customer {buyer.name} added.")
        return redirect(reverse("quotations:list"))
    return render(request, "quotations/buyer_form.html", {"form": form})


def buyer_list(request):
    buyers = Buyer.objects.order_by("name")
    return render(request, "quotations/buyer_list.html", {"buyers": buyers})


def buyer_edit(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    form = BuyerForm(request.POST or None, instance=buyer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Customer {buyer.name} updated.")
        return redirect(reverse("quotations:buyer_list"))
    return render(request, "quotations/buyer_form.html", {"form": form, "buyer": buyer})


def buyer_delete(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    if request.method == "POST":
        name = buyer.name
        buyer.delete()
        messages.success(request, f"Customer {name} deleted.")
        return redirect(reverse("quotations:buyer_list"))
    return render(request, "quotations/buyer_confirm_delete.html", {"buyer": buyer})


def buyer_quotes(request, pk: int):
    buyer = get_object_or_404(Buyer, pk=pk)
    quotes = Quotation.objects.filter(buyer=buyer).order_by("-created_at").prefetch_related("items")
    return render(request, "quotations/buyer_quotes.html", {"buyer": buyer, "quotes": quotes})
