# Purpose: Defines the Flask Blueprint for yield curve analysis views.

# Stdlib imports
from datetime import datetime

# Third-party imports
from flask import Blueprint, render_template, request, jsonify, current_app
import pandas as pd

# Local imports
from curve_processing import load_curve_data, check_curve_inconsistencies, get_latest_curve_date
from config import COLOR_PALETTE

curve_bp = Blueprint('curve_bp', __name__, template_folder='templates')

# --- Routes ---

@curve_bp.route('/curve/summary')
def curve_summary():
    """Displays a summary of yield curve checks for the latest date."""
    current_app.logger.info("Loading curve data for summary...")
    curve_df = load_curve_data()

    if curve_df.empty:
        current_app.logger.warning("Curve data is empty or failed to load.")
        summary = {}
        latest_date_str = "N/A"
    else:
        current_app.logger.info("Checking curve inconsistencies...")
        summary = check_curve_inconsistencies(curve_df)
        latest_date = get_latest_curve_date(curve_df)
        latest_date_str = latest_date.strftime('%Y-%m-%d') if latest_date else "N/A"
        current_app.logger.info(f"Inconsistency summary generated for date: {latest_date_str}")

    return render_template('curve_summary.html',
                           summary=summary,
                           latest_date=latest_date_str)

@curve_bp.route('/curve/details/<currency>')
def curve_details(currency):
    """Displays the yield curve chart for a specific currency and date."""
    current_app.logger.info(f"Loading curve data for currency: {currency}")
    curve_df = load_curve_data()
    available_dates = []
    selected_date_str = request.args.get('date') # Get date from query param

    if curve_df.empty:
        current_app.logger.warning(f"Curve data is empty for currency details: {currency}")
        chart_data = {}
        selected_date = None
        latest_date = None
    else:
        # Get all available dates for this currency, sorted descending
        try:
            available_dates = sorted(
                curve_df.loc[currency].index.get_level_values('Date').unique(),
                reverse=True
            )
        except KeyError:
            current_app.logger.warning(f"No data found for currency: {currency}")
            available_dates = []
        except Exception as e:
             current_app.logger.error(f"Error getting dates for {currency}: {e}")
             available_dates = []


        latest_date = available_dates[0] if available_dates else None

        # Determine the date to display
        if selected_date_str:
            try:
                selected_date = pd.to_datetime(selected_date_str).normalize()
                if selected_date not in available_dates:
                    selected_date = latest_date # Fallback to latest if selected date invalid
            except ValueError:
                 selected_date = latest_date # Fallback to latest on parse error
        else:
            selected_date = latest_date # Default to latest

        # Fetch data for the selected date and currency
        chart_data = {}
        if selected_date:
             selected_date_str = selected_date.strftime('%Y-%m-%d') # Update str representation
             try:
                 # Ensure index is aligned correctly before accessing TermDays
                 curve_for_date_raw = curve_df.loc[currency, selected_date]
                 # Check if it's a Series (single term) or DataFrame (multiple terms)
                 if isinstance(curve_for_date_raw, pd.Series):
                     curve_for_date = curve_for_date_raw.to_frame().T # Convert to DataFrame
                 else:
                     curve_for_date = curve_for_date_raw.copy() # Work on a copy

                 # Reset index if 'TermDays' is not a column yet
                 if 'TermDays' not in curve_for_date.columns and 'TermDays' not in curve_for_date.index.names:
                      if isinstance(curve_for_date.index, pd.MultiIndex):
                          # If Term is part of MultiIndex, reset it partially
                           curve_for_date = curve_for_date.reset_index(level='Term') # Assuming Term is the level name
                      else:
                          curve_for_date = curve_for_date.reset_index()


                 # Now sort by TermDays (should be a column)
                 if 'TermDays' in curve_for_date.columns:
                     curve_for_date = curve_for_date.sort_values('TermDays')
                 else:
                      current_app.logger.error(f"Could not find 'TermDays' to sort for {currency} on {selected_date_str}")
                      # Handle error or return empty chart data
                      chart_data = {} # Ensure chart_data is empty if sorting fails


                 # Proceed only if sorting was successful and df is not empty
                 if not curve_for_date.empty and 'TermDays' in curve_for_date.columns:
                     chart_data = {
                         'labels': curve_for_date['TermDays'].tolist(), # X-axis (days)
                         'datasets': [{
                             'label': f'{currency} Yield Curve ({selected_date_str})',
                             'data': curve_for_date['Value'].tolist(), # Y-axis (yield)
                             'borderColor': COLOR_PALETTE[0],
                             'fill': False,
                             'tension': 0.1 # Makes the line slightly curved
                         }]
                     }
                     current_app.logger.info(f"Prepared chart data for {currency} on {selected_date_str}")
                 else:
                      chart_data = {} # Ensure empty if data processing failed


             except KeyError:
                  current_app.logger.warning(f"No data found for {currency} on {selected_date_str}")
                  chart_data = {}
             except Exception as e:
                  current_app.logger.error(f"Error preparing chart data for {currency} on {selected_date_str}: {e}", exc_info=True)
                  chart_data = {}
        else:
            selected_date_str = "N/A"


    return render_template('curve_details.html',
                           currency=currency,
                           chart_data=chart_data,
                           available_dates=[d.strftime('%Y-%m-%d') for d in available_dates],
                           selected_date=selected_date_str) 