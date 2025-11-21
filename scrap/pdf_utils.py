# pdf_utils.py
from dataclasses import dataclass
from pathlib import Path
from typing import List
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import mm
from quotation_models.models import Company, Buyer, Quotation, TemplateStyle

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
    items: List[dict]   # dicts: item, description, qty, rate
    totals: dict
    output_path: Path

def _money(v): return f"{float(v):,.2f}"

def _header(c, doc, title, seller: Company):
    c.saveState()
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, 280 * mm, seller.name)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 274 * mm, (seller.address or "")[:90])
    c.drawString(20 * mm, 270 * mm, f"GSTIN: {seller.gstin or ''}   PAN: {seller.pan or ''}")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(200 * mm, 280 * mm, title)
    c.restoreState()

def _footer(c, doc):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.gray)
    c.drawRightString(200 * mm, 10 * mm, f"Page {doc.page}")
    c.restoreState()

def _two_row_items_table(ctx: RenderContext, style_code: str):
    header = [
        Paragraph("<b>Item</b>", styles['Center']),
        Paragraph("<b>Quantity</b>", styles['Center']),
        Paragraph("<b>Rate</b>", styles['Center']),
        Paragraph("<b>Amount</b>", styles['Center'])
    ]
    data = [header]

    desc_style = ParagraphStyle(name="DescSmall", parent=styles["Normal"], fontSize=8, leading=9)
    item_style = ParagraphStyle(name="ItemBold", parent=styles["Normal"], alignment=TA_LEFT)

    for it in ctx.items:
        item_name = (it.get("item") or "").strip()
        desc = (it.get("description") or "").strip()
        qty = float(it.get("qty") or 0)
        rate = float(it.get("rate") or 0)
        amt = qty * rate

        row_top = [Paragraph(f"<b>{item_name}</b>", item_style), f"{qty:.2f}", _money(rate), _money(amt)]
        row_bottom = [Paragraph(f"<i>{desc}</i>", desc_style) if desc else Paragraph("", desc_style), "", "", ""]
        data.extend([row_top, row_bottom])

    data.append(["", "", Paragraph("Subtotal", styles['Right']), _money(ctx.totals["subtotal"])])
    data.append(["", "", Paragraph("Tax", styles['Right']), _money(ctx.totals["tax"])])
    data.append(["", "", Paragraph("<b>Total</b>", styles['Right']), Paragraph(f"<b>{_money(ctx.totals['total'])}</b>", styles['Right'])])

    colw = [95*mm, 25*mm, 30*mm, 35*mm]
    t = Table(data, colWidths=colw, hAlign="LEFT")
    ts = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey if style_code == "main" else colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.6, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,1), (-1,-1), "RIGHT"),
    ])
    # Span desc across first three columns on every bottom row (skip header row 0, totals at end)
    
    for r in range(1, len(data) - 3):
        if (r % 2) == 0:
            ts.add('SPAN', (0, r), (2, r))
            ts.add('ALIGN', (0, r), (2, r), 'LEFT')
    t.setStyle(ts)
    return t

def render_pdf(ctx: RenderContext, style_code: str):
    doc = SimpleDocTemplate(str(ctx.output_path), pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    story = []

    if style_code == "main":
        story.append(Paragraph("QUOTATION", styles['MainTitle']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(ctx.seller.name, styles['CompanyName']))
        story.append(Paragraph(ctx.seller.address or "", styles['CompanyDetails']))
        if ctx.seller.phone:
            story.append(Paragraph(f"Phone No. {ctx.seller.phone}", styles['CompanyDetails']))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        story.append(Spacer(1, 12))

        meta_data = [[
            Paragraph(f"<b>To:</b><br/>{ctx.buyer.name}<br/>{ctx.buyer.address or ''}", styles['Left']),
            Paragraph(f"<b>No:</b> {ctx.quotation.code}<br/><b>Date:</b> {ctx.quotation.created_at.strftime('%d-%m-%Y')}", styles['Right'])
        ]]
        meta = Table(meta_data, colWidths=['60%', '40%'])
        meta.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story += [meta, Spacer(1, 12)]

        story.append(Paragraph("Dear Sir/Madam,", styles['Normal']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "This is with reference to our discussion with you we are submitting our quotation as under. "
            "We hope that you will find our offer most competitive and enable you to finalise your prestigious order in our favour.",
            styles['Normal']
        ))
        story.append(Spacer(1, 12))

        story.append(_two_row_items_table(ctx, style_code))
        story.append(Spacer(1, 24))
        story.append(Paragraph("<b>Terms & Conditions:</b>", styles['Normal']))
        story.append(Paragraph(ctx.quotation.notes or "GST 18% Extra.", styles['Normal']))
        story.append(Spacer(1, 48))
        story.append(Paragraph(f"For {ctx.seller.name}", styles['Right']))

        doc.build(story)
        return

    # Other templates: simple banner + table
    doc.topMargin = 72
    meta_rows = [
        ["Quotation #", ctx.quotation.code, "Date", ctx.quotation.created_at.strftime("%d-%b-%Y")],
        ["Buyer", ctx.buyer.name, "Valid Until", ctx.quotation.valid_until.strftime("%d-%b-%Y") if ctx.quotation.valid_until else "—"],
        ["Phone", ctx.buyer.phone or "—", "Email", ctx.buyer.email or "—"],
    ]
    t = Table(meta_rows, colWidths=[28*mm, 70*mm, 28*mm, 60*mm])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 9),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("BOX", (0,0), (-1,-1), 0.3, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 8), _two_row_items_table(ctx, style_code)]
    doc.build(story, onFirstPage=lambda c, d: _header(c, d, "QUOTATION", ctx.seller), onLaterPages=_footer)
