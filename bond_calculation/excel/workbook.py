# workbook.py
# Purpose: Orchestrate Excel workbook creation from inputs and analytics

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from openpyxl import Workbook
from .styles import ensure_named_styles
from .sheets.instructions import add_instructions_sheet
from .sheets.input_parameters import add_input_parameters_sheet
from .sheets.cashflows import add_cashflows_sheet
from .sheets.yield_curve import add_yield_curve_sheet
from .sheets.ytm import add_ytm_sheet
from .sheets.summary import add_summary_sheet
from .sheets.zspread import add_zspread_sheet
from .sheets.oas import add_oas_sheet
from .sheets.assumptions import add_assumptions_sheet
from .sheets.oas_components import add_oas_components_sheet
from .sheets.volatility_impact import add_volatility_impact_sheet
from .sheets.effective_duration import add_effective_duration_sheet
from .sheets.key_rate_durations import add_key_rate_durations_sheet
from .sheets.convexity import add_convexity_sheet
from .sheets.duration_summary import add_duration_summary_sheet

# Import new enhanced sheets
from .sheets.controls import add_controls_sheet
from .sheets.data_source import add_data_source_sheet
from .sheets.sec_data import add_sec_data_sheet
from .sheets.summary_comparison import add_summary_comparison_sheet

# Import enhanced institutional-grade sheets
try:
    from .sheets.settlement_enhanced import add_settlement_enhanced_sheet
    from .sheets.multicurve_framework import add_multicurve_framework_sheet
    from .sheets.higher_order_greeks import add_higher_order_greeks_sheet
    from .sheets.daycount_precision import add_daycount_precision_sheet
    from .sheets.hull_white_monte_carlo import add_hull_white_monte_carlo_sheet
    from .sheets.numerical_methods_demo import add_numerical_methods_demo_sheet
    ENHANCED_SHEETS_AVAILABLE = True
    print("Enhanced institutional-grade Excel sheets loaded")
except ImportError as e:
    print(f"Enhanced Excel sheets not available: {e}")
    ENHANCED_SHEETS_AVAILABLE = False


def build_workbook(
    bond_data: Dict,
    cashflows: List[Dict],
    curve_data: Tuple[List[float], List[float]],
    price: float,
    valuation_date: datetime,
    python_results: Dict,
    accrued_interest: float = None,
) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    ensure_named_styles(wb)

    # Build new control and data sheets first
    add_controls_sheet(wb, bond_data, price, valuation_date)
    add_data_source_sheet(wb, bond_data, cashflows, curve_data, price, valuation_date, accrued_interest=accrued_interest)
    
    # Build core sheets
    add_instructions_sheet(wb, python_results)
    add_input_parameters_sheet(wb, bond_data, price, valuation_date, accrued_interest=accrued_interest)
    add_assumptions_sheet(wb, bond_data)
    add_cashflows_sheet(wb, cashflows, valuation_date)
    add_yield_curve_sheet(wb, curve_data)
    add_ytm_sheet(wb, python_results, bond_data, cashflows, valuation_date)
    add_zspread_sheet(wb, cashflows)
    add_oas_sheet(wb, bond_data, python_results)
    add_oas_components_sheet(wb, bond_data, cashflows, curve_data, price, valuation_date, python_results)
    add_volatility_impact_sheet(wb, python_results)
    add_effective_duration_sheet(wb, python_results, cashflows)
    add_key_rate_durations_sheet(wb, python_results)
    add_convexity_sheet(wb, python_results, cashflows)
    add_duration_summary_sheet(wb, python_results)
    
    # Add enhanced sheets
    add_sec_data_sheet(wb, bond_data, valuation_date)
    add_summary_sheet(wb, bond_data, python_results)
    add_summary_comparison_sheet(wb, bond_data, python_results)
    
    # Add enhanced institutional-grade sheets if available
    if ENHANCED_SHEETS_AVAILABLE:
        try:
            add_settlement_enhanced_sheet(wb, bond_data, price, valuation_date)
            add_multicurve_framework_sheet(wb, curve_data, bond_data, python_results)
            add_higher_order_greeks_sheet(wb, python_results, bond_data, price)
            add_daycount_precision_sheet(wb, bond_data, valuation_date)
            add_hull_white_monte_carlo_sheet(wb, bond_data, python_results)
            add_numerical_methods_demo_sheet(wb, python_results)
            print("✓ Added 6 enhanced institutional sheets to Excel workbook")
        except Exception as e:
            print(f"Warning: Could not add some enhanced sheets: {e}")
    else:
        print("⚠ Enhanced institutional sheets not available - using standard sheets only")

    # Basic formatting
    for ws in wb.worksheets:
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 35

    # Encourage Excel to recalculate all formulas on open, so values populate
    try:
        # openpyxl exposes calculation properties on the workbook
        wb.calculation_properties.fullCalcOnLoad = True
    except Exception:
        # best-effort; non-fatal if property is unavailable in the runtime version
        pass

    return wb


