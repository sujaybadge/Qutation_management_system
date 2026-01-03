from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, formset_factory

from quotation_models.models import Buyer, Company, Quotation, QuotationItem, SellerQuote, TemplateStyle


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "legal_name", "address", "phone", "email", "gstin", "pan", "is_main"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Company name"}),
            "legal_name": forms.TextInput(attrs={"placeholder": "Registered name"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Address"}),
            "phone": forms.TextInput(attrs={"placeholder": "Contact number"}),
            "email": forms.EmailInput(attrs={"placeholder": "contact@example.com"}),
            "gstin": forms.TextInput(attrs={"placeholder": "GSTIN"}),
            "pan": forms.TextInput(attrs={"placeholder": "PAN"}),
        }


class BuyerForm(forms.ModelForm):
    class Meta:
        model = Buyer
        fields = ["name", "phone", "email", "address", "gstin"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Customer name"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Billing / shipping address"}),
            "gstin": forms.TextInput(attrs={"placeholder": "GSTIN (optional)"}),
        }


class QuotationForm(forms.ModelForm):
    valid_until = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Quotation
        fields = ["buyer", "notes", "include_gst", "currency", "valid_until"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Terms & conditions or notes"}),
            "currency": forms.TextInput(attrs={"placeholder": "INR"}),
        }

    include_gst = forms.BooleanField(required=False, initial=True, label="Include GST (18%)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["buyer"].queryset = Buyer.objects.order_by("name")


class QuotationItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow empty values on the form; we enforce presence/positivity in clean when needed.
        self.fields["qty"].required = False
        self.fields["rate"].required = False

    class Meta:
        model = QuotationItem
        fields = ["item_name", "description", "qty", "rate"]
        widgets = {
            "item_name": forms.TextInput(attrs={"placeholder": "Item name", "list": "item-suggestions"}),
            "description": forms.TextInput(attrs={"placeholder": "Description / instructions", "list": "instruction-suggestions"}),
            "qty": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def clean(self):
        data = super().clean()
        # Skip validation if marked for deletion or untouched empty form
        if data.get("DELETE") or not self.has_changed():
            return data
        name = (data.get("item_name") or "").strip()
        desc = (data.get("description") or "").strip()
        qty_raw = data.get("qty")
        rate_raw = data.get("rate")

        # If everything is empty, allow the row (it will be ignored)
        if not name and not desc and qty_raw in (None, "") and rate_raw in (None, ""):
            return data

        qty = Decimal(qty_raw or "0")
        rate = Decimal(rate_raw or "0")

        if not name and not desc:
            self.add_error("item_name", "Enter item or description.")
            self.add_error("description", "Enter item or description.")
        if qty <= 0:
            self.add_error("qty", "Quantity must be greater than zero.")
        if rate < 0:
            self.add_error("rate", "Rate cannot be negative.")
        return data


def get_item_formset(extra: int = 2):
    """Inline formset factory wrapper so we can adjust the number of blank rows per view."""
    return inlineformset_factory(
        Quotation,
        QuotationItem,
        form=QuotationItemForm,
        fields=["item_name", "description", "qty", "rate"],
        extra=extra,
        can_delete=True,
        validate_min=False,
        min_num=0,
    )


QuotationItemFormSet = get_item_formset()


class SellerQuoteForm(forms.ModelForm):
    class Meta:
        model = SellerQuote
        fields = ["seller", "template"]
        widgets = {
            "seller": forms.Select(),
            "template": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["seller"].queryset = Company.objects.order_by("-is_main", "name")
        self.fields["template"].queryset = TemplateStyle.objects.order_by("code")


def get_seller_formset(extra: int = 1):
    return inlineformset_factory(
        Quotation,
        SellerQuote,
        form=SellerQuoteForm,
        fields=["seller", "template"],
        extra=extra,
        can_delete=True,
        validate_min=False,
        min_num=0,
    )


SellerQuoteFormSet = get_seller_formset()


class QuotationBlockForm(forms.Form):
    id = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    buyer = forms.ModelChoiceField(queryset=Buyer.objects.order_by("name"))
    seller = forms.ModelChoiceField(queryset=Company.objects.order_by("-is_main", "name"))
    template = forms.ModelChoiceField(queryset=TemplateStyle.objects.order_by("code"))
    notes = forms.CharField(required=False, initial="GST 18% extra\nValid for 2 days\nPayment 100% in advance", widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Notes / Terms"}))
    currency = forms.CharField(required=False, initial="INR", widget=forms.TextInput(attrs={"placeholder": "INR"}))
    valid_until = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    include_gst = forms.BooleanField(required=False, initial=True, label="Include GST (18%)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Refresh querysets at runtime so newly added records appear.
        self.fields["buyer"].queryset = Buyer.objects.order_by("name")
        self.fields["seller"].queryset = Company.objects.order_by("-is_main", "name")
        self.fields["template"].queryset = TemplateStyle.objects.order_by("code")


PlainItemFormSet = formset_factory(
    QuotationItemForm,
    extra=2,
    can_delete=True,
    validate_min=False,
    min_num=0,
)
