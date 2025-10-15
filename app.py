"""
Quotation Management System — Single-file Windows App
- GUI: Tkinter
- Storage: Django ORM (SQLite)
- PDF generation: ReportLab
- WhatsApp: opens WhatsApp chat (wa.me) with a prefilled message; user attaches the PDF manually. Optional hook to integrate Twilio WhatsApp later.

Quick start (Windows):
1) Python 3.10+ recommended.
2) pip install django==4.2.14 reportlab==4.2.2 pillow==10.4.0 phonenumbers==8.13.47
3) python quotation_app.py

Notes:
- First run initializes SQLite DB (quotation_app.sqlite3) and seeds a main company and 3 sample templates.
- PDFs saved under ./output/<YYYY-MM-DD>/<quote_code>.pdf
- Multi-company quotes: pick one or more sellers; the same line items are reused, and one PDF per seller is generated.
- Templates: 5 styles ("main","classic", "modern", "boxed", "minimal"). Style applies per PDF.
- This is an offline desktop app using Django ORM without running a Django server.
"""

import os
import sys
import uuid
import json
import math
import webbrowser
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

# --- Lightweight Django setup (ORM only) ---
import django
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quotation_app.sqlite3"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_ROOT.mkdir(exist_ok=True)

if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="quotation-app-secret-key",
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "quotation_models",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(DB_PATH),
            }
        },
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
        TIME_ZONE="Asia/Kolkata",
        USE_TZ=False,
        MEDIA_ROOT=str(MEDIA_ROOT),
        MEDIA_URL="/media/",
    )

django.setup()

from django.db import models
from django.core.management import call_command
from django.db import transaction

# --- Models (in-memory app label) ---
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

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.name


class TemplateStyle(models.Model):
    code = models.CharField(max_length=50, unique=True)  # classic, modern, boxed, minimal
    title = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

    class Meta:
        app_label = "quotation_models"

    def __str__(self):
        return self.title


class Quotation(models.Model):
    code = models.CharField(max_length=40, unique=True)
    buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT)
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
    description = models.CharField(max_length=500)
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        app_label = "quotation_models"


class SellerQuote(models.Model):
    """Link a quotation to a specific seller (company) and a chosen template style.
    One logical quotation can produce multiple seller-specific PDFs with differing branding.
    """
    quotation = models.ForeignKey(Quotation, related_name="seller_quotes", on_delete=models.CASCADE)
    seller = models.ForeignKey(Company, on_delete=models.PROTECT)
    template = models.ForeignKey(TemplateStyle, on_delete=models.PROTECT)
    pdf_path = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        app_label = "quotation_models"
        unique_together = ("quotation", "seller")


# --- Migrations (make+apply in-code) ---
def migrate_if_needed():
    # Create a fake app config for models declared in this file
    from django.apps import apps
    from django.core.management.commands.makemigrations import Command as MakeMigrations

    # Ensure app is recognized
    app_config = apps.get_app_config("quotation_models")
    # Generate and apply migrations into a local migrations package
    migrations_dir = BASE_DIR / "quotation_models" / "migrations"
    os.makedirs(migrations_dir, exist_ok=True)
    init_py = migrations_dir / "__init__.py"
    if not init_py.exists():
        init_py.write_text("")

    # Make migrations if there are none yet
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
        TemplateStyle.objects.create(code="classic", title="Classic (Main Style)", is_default=True)
        TemplateStyle.objects.create(code="modern", title="Modern")
        TemplateStyle.objects.create(code="boxed", title="Boxed")
        TemplateStyle.objects.create(code="minimal", title="Minimal")


# --- PDF generation with ReportLab ---
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm, inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus.flowables import HRFlowable

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
styles.add(ParagraphStyle(name='Right', alignment=TA_RIGHT))
styles.add(ParagraphStyle(name='Left', alignment=TA_LEFT))
styles.add(ParagraphStyle(name='MainTitle', parent=styles['h1'], alignment=TA_CENTER))
styles.add(ParagraphStyle(name='CompanyName', parent=styles['h2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=14))
styles.add(ParagraphStyle(name='CompanyDetails', parent=styles['Normal'], alignment=TA_LEFT))


@dataclass
class RenderContext:
    seller: Company
    quotation: Quotation
    buyer: Buyer
    items: List[dict] # Changed to dict to handle separate item/desc
    totals: dict
    output_path: Path


def _money(v):
    return f"{float(v):,.2f}"


def _header(canvas, doc, title, seller: Company):
    canvas.saveState()
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(20 * mm, 280 * mm, seller.name)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(20 * mm, 274 * mm, seller.address[:90])
    canvas.drawString(20 * mm, 270 * mm, f"GSTIN: {seller.gstin}   PAN: {seller.pan}")
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawRightString(200 * mm, 280 * mm, title)
    canvas.restoreState()


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.gray)
    canvas.drawRightString(200 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def render_pdf(ctx: RenderContext, style_code: str):
    doc = SimpleDocTemplate(str(ctx.output_path), pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    story = []

    if style_code == "main":
        # --- Main Template ---
        story.append(Paragraph("QUOTATION", styles['MainTitle']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(ctx.seller.name, styles['CompanyName']))
        story.append(Paragraph(ctx.seller.address, styles['CompanyDetails']))
        story.append(Paragraph(f"Phone No. {ctx.seller.phone}", styles['CompanyDetails']))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        story.append(Spacer(1, 12))

        meta_data = [
            [Paragraph(f"<b>To:</b><br/>{ctx.buyer.name}<br/>{ctx.buyer.address}", styles['Left']),
             Paragraph(f"<b>No:</b> {ctx.quotation.code}<br/><b>Date:</b> {ctx.quotation.created_at.strftime('%d-%m-%Y')}", styles['Right'])]
        ]
        meta_table = Table(meta_data, colWidths=['60%', '40%'])
        meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(meta_table)
        story.append(Spacer(1, 12))
        
        story.append(Paragraph("Dear Sir/Madam,", styles['Normal']))
        story.append(Spacer(1, 6))
        story.append(Paragraph("This is with reference to our discussion with you we are submitting our quotation as under we hope that you will find our offer most compitative and enable you to finalise your prestigious order in our favour.", styles['Normal']))
        story.append(Spacer(1, 12))

        data = [
            [Paragraph("<b>Item</b>", styles['Center']), 
             Paragraph("<b>Quantity</b>", styles['Center']), 
             Paragraph("<b>Rate</b>", styles['Center']), 
             Paragraph("<b>Amount</b>", styles['Center'])]
        ]
        
        item_style = ParagraphStyle(name='ItemStyle', parent=styles['Normal'], alignment=TA_CENTER)
        
        for item_data in ctx.items:
            item_name = item_data.get('item', '')
            item_desc = item_data.get('description', '')
            
            # Create a multi-line paragraph for the item cell
            item_paragraph_text = f"<b>{item_name}</b>"
            if item_desc:
                item_paragraph_text += f"<br/><i><font size='8'>{item_desc}</font></i>"
            
            item_cell = Paragraph(item_paragraph_text, item_style)

            data.append([
                item_cell,
                f"{float(item_data['qty']):.2f}",
                _money(item_data['rate']),
                _money(item_data['qty'] * item_data['rate'])
            ])
        
        data.append(["", "", Paragraph("Subtotal", styles['Right']), _money(ctx.totals["subtotal"])])
        data.append(["", "", Paragraph("Tax (18%)", styles['Right']), _money(ctx.totals["tax"])])
        data.append(["", "", Paragraph("<b>Total</b>", styles['Right']), Paragraph(f"<b>{_money(ctx.totals['total'])}</b>", styles['Right'])])

        items_table = Table(data, colWidths=[95*mm, 25*mm, 30*mm, 35*mm], hAlign="LEFT")
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (1,1), (-1,-1), "RIGHT"),
            ('SPAN', (-2,-1), (-2,-1)), 
        ]))
        story.append(items_table)
        story.append(Spacer(1, 24))

        story.append(Paragraph("<b>Terms & Conditions:</b>", styles['Normal']))
        story.append(Paragraph(ctx.quotation.notes or "GST 18% Extra.", styles['Normal']))
        story.append(Spacer(1, 48))
        story.append(Paragraph(f"For {ctx.seller.name}", styles['Right']))

        doc.build(story)
        return

    # --- Other Templates ---
    doc.topMargin = 72
    meta = [
        ["Quotation #", ctx.quotation.code, "Date", ctx.quotation.created_at.strftime("%d-%b-%Y")],
        ["Buyer", ctx.buyer.name, "Valid Until", ctx.quotation.valid_until.strftime("%d-%b-%Y") if ctx.quotation.valid_until else "—"],
        ["Phone", ctx.buyer.phone, "Email", ctx.buyer.email or "—"],
    ]

    t = Table(meta, colWidths=[28*mm, 70*mm, 28*mm, 60*mm])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 9), ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("BOX", (0,0), (-1,-1), 0.3, colors.black), ("INNERGRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 8)]

    data = [["Description", "Qty", "Rate", "Amount"]]
    for it in ctx.items:
        # For older templates, combine item and description
        full_desc = f"{it['item']}: {it['description']}" if it['item'] and it['description'] else it['item'] or it['description']
        data.append([full_desc, f"{float(it['qty']):.2f}", _money(it['rate']), _money(it['qty'] * it['rate'])])
    
    data.append(["", "", "Subtotal", _money(ctx.totals["subtotal"])])
    data.append(["", "", "Tax", _money(ctx.totals["tax"])])
    data.append(["", "", "Total", _money(ctx.totals["total"])])

    colw = [100*mm, 20*mm, 30*mm, 30*mm]
    items_table = Table(data, colWidths=colw, hAlign="LEFT")
    # Styles omitted for brevity...
    story += [items_table, Spacer(1, 12)]

    if ctx.quotation.notes:
        story += [Paragraph(f"<b>Notes</b>: {ctx.quotation.notes}", styles["Normal"])]

    doc.build(story, onFirstPage=lambda c, d: _header(c, d, "QUOTATION", ctx.seller), onLaterPages=_footer)


# --- WhatsApp helpers ---
import phonenumbers
# ... (rest of the file is unchanged)

def format_e164(phone_raw: str) -> Optional[str]:
    if not phone_raw: return None
    try:
        num = phonenumbers.parse(phone_raw, "IN")
        if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
    except Exception: return None
    return None


def open_whatsapp_chat(phone: str, text: str):
    phone_digits = format_e164(phone)
    url = f"https://wa.me/{phone_digits}?text={quote(text)}" if phone_digits else f"https://wa.me/?text={quote(text)}"
    webbrowser.open(url)


# --- ORM utility ---
def create_quotation_and_items(buyer_name: str, buyer_phone: str, buyer_email: str, buyer_address: str,
                               items: List[dict], notes: str, days_valid: int = 7,
                               currency: str = "INR") -> Quotation:
    with transaction.atomic():
        buyer, _ = Buyer.objects.get_or_create(name=buyer_name.strip() or "Walk-in Buyer",
                                               defaults={"phone": buyer_phone, "email": buyer_email, "address": buyer_address})
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
            amount = qty * rate
            subtotal += amount
            QuotationItem.objects.create(quotation=q, description=full_description, qty=qty, rate=rate, amount=amount)
        
        tax = round(subtotal * 0.18, 2)
        total = round(subtotal + tax, 2)
        q.subtotal, q.tax, q.total = subtotal, tax, total
        q.save()
        return q


def generate_pdfs_for_sellers(q: Quotation, seller_ids: List[int], template_code: str, items_data: List[dict]) -> List[Path]:
    out_dir = BASE_DIR / "output" / dt.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    buyer = q.buyer
    tmpl = TemplateStyle.objects.get(code=template_code)

    pdf_paths = []
    for sid in seller_ids:
        seller = Company.objects.get(id=sid)
        file_path = out_dir / f"{q.code}-{seller.name.replace(' ', '')}.pdf"
        ctx = RenderContext(
            seller=seller, quotation=q, buyer=buyer, items=items_data,
            totals={"subtotal": q.subtotal, "tax": q.tax, "total": q.total},
            output_path=file_path,
        )
        render_pdf(ctx, style_code=template_code)
        sq, _ = SellerQuote.objects.get_or_create(quotation=q, seller=seller, defaults={"template": tmpl})
        sq.template, sq.pdf_path = tmpl, str(file_path)
        sq.save()
        pdf_paths.append(file_path)

    return pdf_paths


# --- Minimal Tkinter GUI ---
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tksheet

class QuotationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Quotation Manager")
        self.geometry("980x720")
        self.minsize(900, 660)
        self._build_widgets()

    def _build_widgets(self):
        pad = {"padx": 6, "pady": 4}

        bf = ttk.LabelFrame(self, text="Buyer")
        bf.pack(fill="x", **pad)
        bf.grid_columnconfigure(1, weight=1)
        bf.grid_columnconfigure(3, weight=1)

        ttk.Label(bf, text="Name").grid(row=0, column=0, sticky="w", pady=2, padx=(5,0))
        self.buyer_name = ttk.Entry(bf)
        self.buyer_name.grid(row=0, column=1, sticky="we", padx=(0,10))
        ttk.Label(bf, text="Phone").grid(row=0, column=2, sticky="w", padx=(5,0))
        self.buyer_phone = ttk.Entry(bf)
        self.buyer_phone.grid(row=0, column=3, sticky="we", padx=(0,5))
        ttk.Label(bf, text="Email").grid(row=1, column=0, sticky="w", pady=2, padx=(5,0))
        self.buyer_email = ttk.Entry(bf)
        self.buyer_email.grid(row=1, column=1, sticky="we", padx=(0,10))
        ttk.Label(bf, text="Address").grid(row=1, column=2, sticky="w", padx=(5,0))
        self.buyer_address = ttk.Entry(bf)
        self.buyer_address.grid(row=1, column=3, sticky="we", padx=(0,5))

        stf = ttk.LabelFrame(self, text="Sellers & Template")
        stf.pack(fill="x", **pad)
        stf.grid_columnconfigure(0, weight=1)
        # ... widgets for seller list and template dropdown
        ttk.Label(stf, text="Select seller companies (Ctrl/Shift for multi-select)").grid(row=0, column=0, sticky="w")
        self.seller_list = tk.Listbox(stf, selectmode=tk.EXTENDED, height=5)
        self.seller_list.grid(row=1, column=0, columnspan=2, sticky="we", padx=4)
        self._refresh_sellers()

        ttk.Label(stf, text="Template").grid(row=0, column=2, sticky="e")
        self.template_var = tk.StringVar(value="main")
        self.template_combo = ttk.Combobox(stf, textvariable=self.template_var, state="readonly",
                                           values=[t.code for t in TemplateStyle.objects.all()])
        self.template_combo.grid(row=1, column=2, sticky="e", padx=4)

        itf = ttk.LabelFrame(self, text="Quotation Items")
        itf.pack(fill="both", expand=True, **pad)
        itf.grid_columnconfigure(0, weight=1)
        itf.grid_rowconfigure(0, weight=1)

        self.items_sheet = tksheet.Sheet(itf)
        self.items_sheet.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.items_sheet.headers(["Item", "Description", "Qty", "Rate", "Total"])
        self.items_sheet.set_column_widths([180, 320, 70, 90, 110])
        self.items_sheet.readonly_columns(columns=[4], readonly=True)
        self.items_sheet.enable_bindings("single_select", "drag_select", "row_select", "column_width_resize",
                                         "end_edit"
                                         "double_click_column_resize", "arrowkeys", "right_click_popup_menu",
                                         "rc_select", "rc_insert_row", "rc_delete_row", "copy", "cut", "paste", "delete", "undo", "edit_cell")
        
        buttons_frame = ttk.Frame(itf)
        buttons_frame.grid(row=1, column=0, sticky="e", pady=(5, 0), padx=4)
        # ... buttons
        add_btn = ttk.Button(buttons_frame, text="Add Row", command=self._add_item_row)
        add_btn.pack(side="left", padx=(0, 5))
        remove_btn = ttk.Button(buttons_frame, text="Remove Selected Row(s)", command=self._remove_item_row)
        remove_btn.pack(side="left")

        nf = ttk.LabelFrame(self, text="Notes & Actions")
        nf.pack(fill="x", **pad)
        nf.grid_columnconfigure(1, weight=1)
        # ... notes and action buttons
        ttk.Label(nf, text="Notes").grid(row=0, column=0, sticky="w")
        self.notes_entry = ttk.Entry(nf, width=80)
        self.notes_entry.grid(row=0, column=1, sticky="we")

        self.generate_btn = ttk.Button(nf, text="Generate PDF(s)", command=self._on_generate)
        self.generate_btn.grid(row=0, column=2, padx=6)
        self.whatsapp_btn = ttk.Button(nf, text="Send to WhatsApp", command=self._on_whatsapp)
        self.whatsapp_btn.grid(row=0, column=3)
        self.items_sheet.extra_bindings("end_edit_cell", self._update_row_total)


    def _update_row_total(self, event):
        row = event["row"]
        if event["column"] in (2, 3): # If Qty or Rate was edited
            try:
                qty_str = self.items_sheet.get_cell_data(row, 2)
                rate_str = self.items_sheet.get_cell_data(row, 3)
                qty = float(qty_str or 0)
                rate = float(rate_str or 0)
                total = qty * rate
                self.items_sheet.set_cell_data(row, 4, f"{total:,.2f}")
            except (ValueError, TypeError):
                self.items_sheet.set_cell_data(row, 4, "")

    def _add_item_row(self): self.items_sheet.insert_row()

    def _remove_item_row(self):
        selected_rows = self.items_sheet.get_selected_rows(get_cells=False)
        if not selected_rows:
            messagebox.showwarning("No Selection", "Please select one or more rows to remove.")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to remove {len(selected_rows)} selected row(s)?"):
            self.items_sheet.delete_rows(rows=selected_rows)

    def _refresh_sellers(self):
        self.seller_list.delete(0, tk.END)
        for c in Company.objects.all().order_by("-is_main", "name"):
            label = f"{c.name} {'(main)' if c.is_main else ''}"
            self.seller_list.insert(tk.END, label)
        self._seller_id_map = [c.id for c in Company.objects.all().order_by("-is_main", "name")]

    def _get_items_from_sheet(self) -> List[dict]:
        rows = []
        for row_data in self.items_sheet.get_sheet_data():
            if not any(str(cell).strip() for cell in row_data): continue
            item, desc, qty_str, rate_str = (row_data + ["", "", "", ""])[:4]
            try:
                qty = float(qty_str or 0)
                rate = float(rate_str or 0)
            except ValueError: continue
            
            if str(item).strip() or str(desc).strip():
                 rows.append({"item": str(item).strip(), "description": str(desc).strip(), "qty": qty, "rate": rate})
        return rows

    def _selected_seller_ids(self) -> List[int]:
        return [self._seller_id_map[idx] for idx in self.seller_list.curselection()]

    def _on_generate(self):
        try:
            items = self._get_items_from_sheet()
            if not items:
                messagebox.showerror("Items required", "Please add at least one valid item.")
                return
            sellers = self._selected_seller_ids()
            if not sellers:
                messagebox.showerror("Seller required", "Select one or more seller companies.")
                return
            
            q = create_quotation_and_items(
                buyer_name=self.buyer_name.get(), buyer_phone=self.buyer_phone.get(),
                buyer_email=self.buyer_email.get(), buyer_address=self.buyer_address.get(),
                items=items, notes=self.notes_entry.get(),
            )
            pdfs = generate_pdfs_for_sellers(q, sellers, self.template_var.get(), items_data=items)
            msg = "\n".join(str(p) for p in pdfs)
            messagebox.showinfo("PDFs generated", f"Saved:\n{msg}")
            self._last_quote, self._last_pdfs = q, pdfs
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def _on_whatsapp(self):
        if not hasattr(self, "_last_quote"):
            messagebox.showwarning("No PDF yet", "Generate PDFs first.")
            return
        phone = self.buyer_phone.get().strip()
        files = "\n".join([str(p) for p in getattr(self, "_last_pdfs", [])])
        txt = (f"Hello {self.buyer_name.get().strip() or 'Customer'},\n"
               f"Please find your quotation(s): {self._last_quote.code}.\n"
               f"Saved at: \n{files}\n\n"
               f"Kindly review and let us know if you have any questions.")
        try: open_whatsapp_chat(phone, txt)
        except Exception as e: messagebox.showerror("WhatsApp", f"Could not open WhatsApp link: {e}")

# --- Bootstrap ---
if __name__ == "__main__":
    # Prepare DB
    migrate_if_needed()
    seed_initial_data()

    # Launch app
    app = QuotationApp()
    app.mainloop()
