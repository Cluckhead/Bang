# sheets/cashflows.py
# Purpose: Build the Cashflows sheet

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from openpyxl import Workbook

from ..styles import header_font, header_fill, border


def add_cashflows_sheet(wb: Workbook, cashflows: List[Dict], valuation_date: datetime) -> None:
    ws = wb.create_sheet("Cashflows")
    headers = [
        "Payment #",
        "Payment Date",
        "Days from Val",
        "Time (Years)",
        "Accrual Period",
        "Coupon Rate",
        "Coupon Payment",
        "Principal Payment",
        "Total Cashflow",
    ]
    ws.append(headers)
    for i, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=i)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    for i, cf in enumerate(cashflows, 1):
        payment_date_uk = cf['date'].strftime('%d/%m/%Y')
        days_from_val = (cf['date'] - valuation_date).days
        ws.append([
            i,
            payment_date_uk,
            days_from_val,
            f"=C{i+1}/365.25",
            cf['accrual_period'],
            f"=Input_Parameters!$B$8/100",
            f"=F{i+1}*E{i+1}*Input_Parameters!$B$12",
            cf['principal'] if cf['principal'] > 0 else 0,
            f"=G{i+1}+H{i+1}",
        ])


