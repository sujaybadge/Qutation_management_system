# ui.py
from pathlib import Path
from typing import List, Optional
import tkinter as tk
from tkinter import ttk, messagebox
import tksheet

from quotation_models.models import Company, TemplateStyle, Quotation
from orm_utils import create_quotation_and_items
from pdf_utils import RenderContext, render_pdf
from whatsapp import open_whatsapp_chat

class QuotationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Quotation Manager")
        self.geometry("1050x760")
        self.minsize(980, 680)
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
        stf.grid_columnconfigure(1, weight=1)

        ttk.Label(stf, text="Select seller companies (Ctrl/Shift for multi-select)").grid(row=0, column=0, sticky="w")
        self.seller_list = tk.Listbox(stf, selectmode=tk.EXTENDED, height=5, exportselection=False)
        self.seller_list.grid(row=1, column=0, columnspan=2, sticky="we", padx=4)
        self._refresh_sellers()

        ttk.Label(stf, text="Template").grid(row=0, column=2, sticky="e")
        self.template_var = tk.StringVar(value="main")
        tmpl_values = [t.code for t in TemplateStyle.objects.all().order_by("code")]
        self.template_combo = ttk.Combobox(stf, textvariable=self.template_var, state="readonly", values=tmpl_values, width=14)
        self.template_combo.grid(row=1, column=2, sticky="e", padx=4)

        itf = ttk.LabelFrame(self, text="Quotation Items (Row 1 = Item/Qty/Rate/Amount, Row 2 = Description)")
        itf.pack(fill="both", expand=True, **pad)
        itf.grid_columnconfigure(0, weight=1)
        itf.grid_rowconfigure(0, weight=1)

        self.items_sheet = tksheet.Sheet(itf, height=360)
        self.items_sheet.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.items_sheet.headers(["Item / Description", "Qty", "Rate", "Amount"])
        self.items_sheet.column_width(column=0, width=540)
        self.items_sheet.column_width(column=1, width=90)
        self.items_sheet.column_width(column=2, width=100)
        self.items_sheet.column_width(column=3, width=110)
        self.items_sheet.align_columns(1, align="e")
        self.items_sheet.align_columns(2, align="e")
        self.items_sheet.align_columns(3, align="e")

        self.items_sheet.set_sheet_data([["", "", "", ""], ["", "", "", ""]])

        self.items_sheet.enable_bindings(
            "single_select", "drag_select", "row_select",
            "column_width_resize", "double_click_column_resize",
            "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy", "cut", "paste", "delete", "undo", "edit_cell"
        )
        self.items_sheet.extra_bindings("end_edit_cell", self._on_cell_edited)

        btns = ttk.Frame(itf)
        btns.grid(row=1, column=0, sticky="e", pady=(0, 4), padx=4)
        ttk.Button(btns, text="Add Item", command=lambda: self._insert_item_pair()).pack(side="left", padx=4)
        ttk.Button(btns, text="Remove Item", command=self._remove_item_pairs).pack(side="left")

        nf = ttk.LabelFrame(self, text="Notes & Actions")
        nf.pack(fill="x", **pad)
        nf.grid_columnconfigure(1, weight=1)

        ttk.Label(nf, text="Notes").grid(row=0, column=0, sticky="w")
        self.notes_entry = ttk.Entry(nf, width=80)
        self.notes_entry.grid(row=0, column=1, sticky="we")

        ttk.Button(nf, text="Generate PDF(s)", command=self._on_generate).grid(row=0, column=2, padx=6)
        ttk.Button(nf, text="Send to WhatsApp", command=self._on_whatsapp).grid(row=0, column=3)

    # ---------- items (paired rows) ----------
    def _insert_item_pair(self, index: Optional[int] = None):
        if index is None:
            self.items_sheet.insert_row(["", "", "", ""])
            self.items_sheet.insert_row(["", "", "", ""])
            self.items_sheet.extra_bindings("begin_edit_cell", self._on_begin_edit_cell)

        else:
            self.items_sheet.insert_row(index, ["", "", "", ""])
            self.items_sheet.insert_row(index+1,["", "", "", ""])

    def _selected_item_top_rows(self) -> List[int]:
        selected = sorted(set(self.items_sheet.get_selected_rows(get_cells=False)))
        tops = set()
        for r in selected:
            tops.add(r-1 if r % 2 == 1 else r)
        return sorted(tops)

    def _remove_item_pairs(self):
        tops = list(reversed(self._selected_item_top_rows()))
        if not tops:
            messagebox.showwarning("No Selection", "Select any row of an item to remove.")
            return
        if not messagebox.askyesno("Confirm Delete", f"Remove {len(tops)} selected item(s)?"):
            return
        for top in tops:
            self.items_sheet.delete_rows(rows=[top+1])
            self.items_sheet.delete_rows(rows=[top])

    def _on_begin_edit_cell(self, event):
        """If it's a description row (odd index) and col != 0, force edit to column 0."""
        r, c = event["row"], event["column"]
        if r % 2 == 1 and c != 0:
            # Move selection to col 0 and start edit there
            self.items_sheet.select_cell(r, 0)
            # Tell tksheet to cancel this edit; next click will be on col 0
            return "break"   # cancels the current begin_edit


    def _on_cell_edited(self, event):
        r, c = event["row"], event["column"]
        if r % 2 == 1:
            self.items_sheet.set_cell_data(r, 1, "")
            self.items_sheet.set_cell_data(r, 2, "")
            self.items_sheet.set_cell_data(r, 3, "")
            return
        if c in (1, 2):
            try:
                qty_raw = self.items_sheet.get_cell_data(r, 1)
                rate_raw = self.items_sheet.get_cell_data(r, 2)
                qty = float(qty_raw or 0)
                rate = float(rate_raw or 0)
                amt = qty * rate
                self.items_sheet.set_cell_data(r, 3, f"{amt:,.2f}" if amt else "")
            except (ValueError, TypeError):
                self.items_sheet.set_cell_data(r, 3, "")

    def _get_items_from_sheet(self) -> List[dict]:
        data = self.items_sheet.get_sheet_data()
        items = []
        if len(data) % 2 != 0:
            data = data[:-1]
        for i in range(0, len(data), 2):
            top = data[i]; bot = data[i+1]
            item = (top[0] or "").strip() if len(top) > 0 else ""
            qty_raw = (top[1] or "").strip() if len(top) > 1 and isinstance(top[1], str) else top[1] if len(top) > 1 else ""
            rate_raw = (top[2] or "").strip() if len(top) > 2 and isinstance(top[2], str) else top[2] if len(top) > 2 else ""
            desc = (bot[0] or "").strip() if len(bot) > 0 else ""   # <— only col 0

            if not item and not desc and not qty_raw and not rate_raw:
                continue
            try:
                qty = float(qty_raw or 0)
                rate = float(rate_raw or 0)
            except (ValueError, TypeError):
                continue
            if qty <= 0 or rate < 0:
                continue

            items.append({"item": item, "description": desc, "qty": qty, "rate": rate})
        return items


    def _refresh_sellers(self):
        self.seller_list.delete(0, tk.END)
        companies = list(Company.objects.all().order_by("-is_main", "name"))
        for c in companies:
            label = f"{c.name} {'(main)' if c.is_main else ''}"
            self.seller_list.insert(tk.END, label)
        self._seller_id_map = [c.id for c in companies]

    def _selected_seller_ids(self) -> List[int]:
        return [self._seller_id_map[idx] for idx in self.seller_list.curselection()]

    # ---------- actions ----------
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
                buyer_name=self.buyer_name.get(),
                buyer_phone=self.buyer_phone.get(),
                buyer_email=self.buyer_email.get(),
                buyer_address=self.buyer_address.get(),
                items=items,
                notes=self.notes_entry.get(),
            )

            out_dir = Path(__file__).resolve().parent / "output" / q.created_at.date().isoformat()
            out_dir.mkdir(parents=True, exist_ok=True)
            buyer = q.buyer

            from quotation_models.models import TemplateStyle, Company
            tmpl = TemplateStyle.objects.get(code=self.template_var.get())

            self._last_pdfs = []
            for sid in self._selected_seller_ids():
                seller = Company.objects.get(id=sid)
                file_path = out_dir / f"{q.code}-{seller.name.replace(' ', '')}.pdf"
                ctx = RenderContext(
                    seller=seller, quotation=q, buyer=buyer, items=items,
                    totals={"subtotal": q.subtotal, "tax": q.tax, "total": q.total},
                    output_path=file_path,
                )
                render_pdf(ctx, style_code=self.template_var.get())
                self._last_pdfs.append(file_path)

            self._last_quote = q
            msg = "\n".join(str(p) for p in self._last_pdfs)
            messagebox.showinfo("PDFs generated", f"Saved:\n{msg}")

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
               f"Saved at:\n{files}\n\n"
               f"Kindly review and let us know if you have any questions.")
        try:
            open_whatsapp_chat(phone, txt)
        except Exception as e:
            messagebox.showerror("WhatsApp", f"Could not open WhatsApp link: {e}")
