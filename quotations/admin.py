from django.contrib import admin

from quotation_models.models import Buyer, Company, Quotation, QuotationItem, SellerQuote, TemplateStyle
from quotation_models.models import CatalogItem, Instruction


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0


class SellerQuoteInline(admin.TabularInline):
    model = SellerQuote
    extra = 0


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("code", "buyer", "total", "created_at", "valid_until")
    list_filter = ("created_at",)
    search_fields = ("code", "buyer__name")
    inlines = [QuotationItemInline, SellerQuoteInline]


admin.site.register(Company)
admin.site.register(Buyer)
admin.site.register(TemplateStyle)
admin.site.register(CatalogItem)
admin.site.register(Instruction)
