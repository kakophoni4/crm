from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine


def build_registry_workbook(order: LeadOptOrder, lines: list[LeadOptOrderLine]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "TDSheet"
    headers = [
        "№ документа",
        "Дата документа",
        "Покупатель",
        "ИНН покупателя",
        "КПП покупателя",
        "Поставщик",
        "ИНН поставщика",
        "КПП поставщика",
        "Сумма",
        "Сумма НДС",
        "Сумма без НДС",
    ]
    worksheet.append(headers)

    total_amount = Decimal("0")
    total_vat = Decimal("0")
    total_wo_vat = Decimal("0")

    for line in lines:
        doc_date = line.document_date
        if isinstance(doc_date, date):
            date_text = doc_date.strftime("%d.%m.%Y")
        else:
            date_text = str(doc_date)
        amount = Decimal(str(line.amount))
        vat = Decimal(str(line.vat_amount))
        wo_vat = Decimal(str(line.amount_without_vat))
        total_amount += amount
        total_vat += vat
        total_wo_vat += wo_vat
        worksheet.append(
            [
                line.document_number or "",
                date_text,
                order.buyer_name or "",
                order.buyer_inn,
                order.buyer_kpp or "",
                line.supplier_name or "",
                line.supplier_inn,
                line.supplier_kpp or "",
                float(amount),
                float(vat),
                float(wo_vat),
            ],
        )

    worksheet.append(
        [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            float(total_amount),
            float(total_vat),
            float(total_wo_vat),
        ],
    )

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
