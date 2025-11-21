# orm_utils.py
import uuid
import datetime as dt
from pathlib import Path
from typing import List
from django.core.management import call_command
from django.db import transaction
from quotation_models.models import Company, Buyer, TemplateStyle, Quotation, QuotationItem, SellerQuote

BASE_DIR = Path(__file__).resolve().parent

def migrate_if_needed():
    try:
        call_command("makemigrations", "quotation_models", verbosity=0)
    except SystemExit:
        pass
    call_command("migrate", verbosity=0)

def seed_initial_data():
    if not Company.objects.exists():
        Company.objects.create(
            name="MainCo Pvt Ltd",
            legal_name="MainCo Private Limited",
            address="123 MG Road, Pune, MH",
            phone="+91 9876543210",
            email="sales@mainco.example",
            gstin="27ABCDE1234F1Z5",
            pan="ABCDE1234F",
            is_main=True,
        )
        Company.objects.create(name="Allied Traders", is_main=False)
        Company.objects.create(name="Swift Suppliers", is_main=False)
    if not TemplateStyle.objects.exists():
        TemplateStyle.objects.create(code="main",    title="Main (Letter Style)", is_default=True)
        TemplateStyle.objects.create(code="classic", title="Classic")
        TemplateStyle.objects.create(code="modern",  title="Modern")
        TemplateStyle.objects.create(code="boxed",   title="Boxed")
        TemplateStyle.objects.create(code="minimal", title="Minimal")

def create_quotation_and_items(
    buyer_name: str, buyer_phone: str, buyer_email: str, buyer_address: str,
    items: List[dict], notes: str, days_valid: int = 7, currency: str = "INR"
) -> Quotation:
    with transaction.atomic():
        buyer, _ = Buyer.objects.get_or_create(
            name=(buyer_name or "Walk-in Buyer").strip(),
            defaults={"phone": buyer_phone, "email": buyer_email, "address": buyer_address}
        )
        code = dt.datetime.now().strftime("Q%y%m%d-") + uuid.uuid4().hex[:6].upper()
        q = Quotation.objects.create(
            code=code, buyer=buyer, notes=notes, currency=currency,
            valid_until=dt.datetime.now() + dt.timedelta(days=days_valid),
        )
        subtotal = 0.0
        for row in items:
            item = str(row.get("item", "")).strip()
            desc = str(row.get("description", "")).strip()
            full_description = f"{item}: {desc}" if item and desc else item or desc
            qty = float(row.get("qty", 0) or 0)
            rate = float(row.get("rate", 0) or 0)
            amount = round(qty * rate, 2)
            subtotal += amount
            QuotationItem.objects.create(
                quotation=q, description=full_description, qty=qty, rate=rate, amount=amount
            )
        tax = round(subtotal * 0.18, 2)
        total = round(subtotal + tax, 2)
        q.subtotal, q.tax, q.total = subtotal, tax, total
        q.save()
        return q

def seller_ids_sorted():
    return list(Company.objects.all().order_by("-is_main", "name").values_list("id", flat=True))
