# quotation_models/models.py
from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=255, blank=True, default="")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    gstin = models.CharField(max_length=32, blank=True, default="")
    pan = models.CharField(max_length=16, blank=True, default="")
    logo_path = models.CharField(max_length=500, blank=True, default="")
    is_main = models.BooleanField(default=False)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.name

class Buyer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, default="")
    gstin = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.name

class TemplateStyle(models.Model):
    code = models.CharField(max_length=50, unique=True)  # main, classic, modern, boxed, minimal
    title = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.title

class Quotation(models.Model):
    code = models.CharField(max_length=40, unique=True)
    buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True, default="")
    currency = models.CharField(max_length=8, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.code

class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, related_name="items", on_delete=models.CASCADE)
    item_name = models.CharField(max_length=200, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        app_label = "quotation_models"


class CatalogItem(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.CharField(max_length=500, blank=True, default="")
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.name


class Instruction(models.Model):
    text = models.CharField(max_length=500, unique=True)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.text

class SellerQuote(models.Model):
    quotation = models.ForeignKey(Quotation, related_name="seller_quotes", on_delete=models.CASCADE)
    seller = models.ForeignKey(Company, on_delete=models.PROTECT)
    template = models.ForeignKey(TemplateStyle, on_delete=models.PROTECT)
    pdf_path = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        app_label = "quotation_models"
        unique_together = ("quotation", "seller")
