# Purpose: Defines the Flask Blueprint for yield curve analysis views.

# Stdlib imports
from datetime import datetime
import re  # local import to avoid global dependency overhead

# Third-party imports
from flask import Blueprint, render_template, request, jsonify, current_app
import pandas as pd
import numpy as np

# Local imports
from data_processing.curve_processing import (
    load_curve_data,
    check_curve_inconsistencies,
    get_latest_curve_date,
)
from core.config import COLOR_PALETTE

curve_bp = Blueprint("curve_bp", __name__, template_folder="../templates")

# Regex pattern to identify canonical YYYY-MM-DD column headers
date_col_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

# --- Routes ---


@curve_bp.route("/curve/summary")
def curve_summary():
    """Displays a summary of yield curve checks for the latest date."""
    # Retrieve the absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    current_app.logger.info("Loading curve data for summary...")
    curve_df = load_curve_data(data_folder_path=data_folder)

    if curve_df.empty:
        current_app.logger.warning("Curve data is empty or failed to load.")
        summary = {}
        latest_date_str = "N/A"
    else:
        current_app.logger.info("Checking curve inconsistencies...")
        summary = check_curve_inconsistencies(curve_df)
        latest_date = get_latest_curve_date(curve_df)
        latest_date_str = latest_date.strftime("%Y-%m-%d") if latest_date else "N/A"
        current_app.logger.info(
            f"Inconsistency summary generated for date: {latest_date_str}"
        )

    return render_template(
        "curve_summary.html", summary=summary, latest_date=latest_date_str
    )


@curve_bp.route("/curve/details/<currency>")
def curve_details(currency):
    """Displays the yield curve chart for a specific currency and date, with historical overlays."""
    current_app.logger.info(f"Loading curve data for currency: {currency}")
    # Retrieve the absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # Pass the data folder path to the loading function
    curve_df = load_curve_data(data_folder_path=data_folder)

    # Get parameters from request
    selected_date_str = request.args.get("date")
    try:
        num_prev_days = int(request.args.get("prev_days", 1))
    except ValueError:
        num_prev_days = 1

    available_dates = []
    curve_table_data = []
    chart_data = {"labels": [], "datasets": []}
    selected_date = None

    if curve_df.empty:
        current_app.logger.warning(
            f"Curve data is empty for currency details: {currency}"
        )
    else:
        # --- Get Available Dates for Currency ---
        try:
            if currency in curve_df.index.get_level_values("Currency"):
                available_dates = sorted(
                    curve_df.loc[currency].index.get_level_values("Date").unique(),
                    reverse=True,
                )
            else:
                current_app.logger.warning(
                    f"Currency '{currency}' not found in curve data index."
                )
                available_dates = []
        except Exception as e:
            current_app.logger.error(
                f"Error getting dates for {currency}: {e}", exc_info=True
            )
            available_dates = []

        # --- Determine Selected Date and Previous Date ---
        latest_date = available_dates[0] if available_dates else None
        previous_date = None  # For daily change calculation
        if selected_date_str:
            try:
                selected_date = pd.to_datetime(selected_date_str).normalize()
                if selected_date not in available_dates:
                    current_app.logger.warning(
                        f"Requested date {selected_date_str} not available for {currency}, falling back to latest."
                    )
                    selected_date = latest_date
                else:
                    # Find the actual previous date in the available list
                    selected_date_index = available_dates.index(selected_date)
                    if selected_date_index + 1 < len(available_dates):
                        previous_date = available_dates[selected_date_index + 1]
                        current_app.logger.info(
                            f"Previous date for change calc: {previous_date}"
                        )
                    else:
                        current_app.logger.info(
                            "Selected date is the oldest available, no previous date for change calc."
                        )
            except ValueError:
                current_app.logger.warning(
                    f"Invalid date format '{selected_date_str}', falling back to latest."
                )
                selected_date = latest_date
        else:
            selected_date = latest_date
            # If defaulting to latest, find the previous date
            if len(available_dates) > 1:
                previous_date = available_dates[1]
                current_app.logger.info(
                    f"Defaulting to latest date. Previous date for change calc: {previous_date}"
                )

        # Update selected_date_str after determining selected_date
        selected_date_str = (
            selected_date.strftime("%Y-%m-%d") if selected_date else "N/A"
        )

        # --- Prepare Data for Chart and Table ---
        if selected_date and available_dates:
            # 1. Process Selected Date for Labels, Chart, and Table Base
            curve_for_selected_date_df = pd.DataFrame()  # Ensure it's defined
            try:
                mask_selected = (
                    curve_df.index.get_level_values("Currency") == currency
                ) & (curve_df.index.get_level_values("Date") == selected_date)
                curve_for_selected_date_df = curve_df[mask_selected].reset_index()
                if not curve_for_selected_date_df.empty:
                    curve_for_selected_date_df["TermMonths"] = (
                        curve_for_selected_date_df["TermDays"] / 30
                    ).round(1)
                    curve_for_selected_date_df = curve_for_selected_date_df.sort_values(
                        "TermDays"
                    )
                    chart_data["labels"] = curve_for_selected_date_df[
                        "TermMonths"
                    ].tolist()
                    # Base table data on selected date
                    curve_table_df = curve_for_selected_date_df[
                        ["Term", "TermDays", "TermMonths", "Value"]
                    ].copy()
                else:
                    current_app.logger.warning(
                        f"No data for selected date {selected_date_str} to generate labels/table."
                    )
            except Exception as e:
                current_app.logger.error(
                    f"Error processing selected date {selected_date_str} for labels/table base: {e}",
                    exc_info=True,
                )

            # 2. Calculate Daily Changes (if previous date exists)
            if previous_date and not curve_for_selected_date_df.empty:
                try:
                    mask_previous = (
                        curve_df.index.get_level_values("Currency") == currency
                    ) & (curve_df.index.get_level_values("Date") == previous_date)
                    curve_for_previous_date = curve_df[mask_previous].reset_index()

                    if not curve_for_previous_date.empty:
                        # Merge selected and previous date data on TermDays
                        merged_changes = pd.merge(
                            curve_for_selected_date_df[["TermDays", "Value"]],
                            curve_for_previous_date[["TermDays", "Value"]],
                            on="TermDays",
                            suffixes=("_selected", "_prev"),
                            how="left",  # Keep all terms from selected date
                        )
                        merged_changes["ValueChange"] = (
                            merged_changes["Value_selected"]
                            - merged_changes["Value_prev"]
                        )

                        # Calculate deviation from average shift
                        average_curve_shift = merged_changes["ValueChange"].mean()
                        merged_changes["ChangeDeviation"] = (
                            merged_changes["ValueChange"] - average_curve_shift
                        )

                        # Calculate Z-score of the deviation
                        deviation_std = merged_changes["ChangeDeviation"].std()
                        if deviation_std != 0 and pd.notna(
                            deviation_std
                        ):  # Avoid division by zero
                            merged_changes["DeviationZScore"] = (
                                merged_changes["ChangeDeviation"]
                                - merged_changes["ChangeDeviation"].mean()
                            ) / deviation_std
                        else:
                            merged_changes["DeviationZScore"] = (
                                0.0  # Or np.nan if preferred
                            )

                        # Merge calculated changes back into the main table DataFrame
                        curve_table_df = pd.merge(
                            curve_table_df,
                            merged_changes[
                                [
                                    "TermDays",
                                    "ValueChange",
                                    "ChangeDeviation",
                                    "DeviationZScore",
                                ]
                            ],
                            on="TermDays",
                            how="left",  # Keep all terms from selected date
                        )
                    else:
                        current_app.logger.warning(
                            f"No data found for previous date {previous_date.strftime('%Y-%m-%d')}"
                        )
                        # Add empty columns if previous data missing
                        curve_table_df["ValueChange"] = np.nan
                        curve_table_df["ChangeDeviation"] = np.nan
                        curve_table_df["DeviationZScore"] = np.nan
                except Exception as e:
                    current_app.logger.error(
                        f"Error calculating daily changes: {e}", exc_info=True
                    )
                    curve_table_df["ValueChange"] = np.nan
                    curve_table_df["ChangeDeviation"] = np.nan
                    curve_table_df["DeviationZScore"] = np.nan
            else:
                # Add empty columns if no previous date
                if "ValueChange" not in curve_table_df.columns:
                    curve_table_df["ValueChange"] = np.nan
                    curve_table_df["ChangeDeviation"] = np.nan
                    curve_table_df["DeviationZScore"] = np.nan

            # Prepare final table data (convert df to dict)
            # Rename Value to Value_Display after calculations are done
            curve_table_df.rename(columns={"Value": "Value_Display"}, inplace=True)
            curve_table_data = curve_table_df[
                [
                    "Term",
                    "TermMonths",
                    "Value_Display",
                    "ValueChange",
                    "ChangeDeviation",
                    "DeviationZScore",
                ]
            ].to_dict("records")

            # 3. Fetch and prepare datasets for Chart
            # Determine the range of plot dates based on num_prev_days
            selected_date_index_for_plot = available_dates.index(selected_date)
            start_index = selected_date_index_for_plot
            end_index = min(
                len(available_dates), selected_date_index_for_plot + num_prev_days + 1
            )
            dates_to_plot = available_dates[start_index:end_index]
            current_app.logger.info(f"Plotting dates for {currency}: {dates_to_plot}")

            for i, plot_date in enumerate(dates_to_plot):
                try:
                    mask = (curve_df.index.get_level_values("Currency") == currency) & (
                        curve_df.index.get_level_values("Date") == plot_date
                    )
                    curve_for_plot_date_filtered = curve_df[mask]

                    if not curve_for_plot_date_filtered.empty:
                        curve_for_plot_date = (
                            curve_for_plot_date_filtered.reset_index().sort_values(
                                "TermDays"
                            )
                        )
                        # Align data points to selected date's TermDays
                        if not curve_for_selected_date_df.empty:
                            aligned_curve = curve_for_plot_date.set_index("TermDays")[
                                ["Value"]
                            ].reindex(curve_for_selected_date_df["TermDays"])
                            plot_data_values = (
                                aligned_curve["Value"].fillna(np.nan).tolist()
                            )
                        else:
                            plot_data_values = []

                        # Determine color and style
                        color_index = i % len(COLOR_PALETTE)
                        border_color = COLOR_PALETTE[color_index]
                        if i > 0:
                            try:
                                r, g, b = (
                                    int(border_color[1:3], 16),
                                    int(border_color[3:5], 16),
                                    int(border_color[5:7], 16),
                                )
                                border_color = f"rgba({r},{g},{b},0.4)"
                            except (IndexError, ValueError):
                                current_app.logger.warning(
                                    f"Could not parse color {border_color} for fading, using default."
                                )

                        dataset = {
                            "label": f'{currency} ({plot_date.strftime("%Y-%m-%d")})',
                            "data": plot_data_values,
                            "borderColor": border_color,
                            "backgroundColor": border_color,
                            "fill": False,
                            "tension": 0.1,
                            "borderWidth": 2 if i == 0 else 1.5,
                        }
                        chart_data["datasets"].append(dataset)
                    else:
                        current_app.logger.warning(
                            f"No data found for {currency} on {plot_date.strftime('%Y-%m-%d')}"
                        )
                except Exception as e:
                    current_app.logger.error(
                        f"Error processing plot data for {currency} on {plot_date.strftime('%Y-%m-%d')}: {e}",
                        exc_info=True,
                    )

    # --- Final Rendering ---
    return render_template(
        "curve_details.html",
        currency=currency,
        chart_data=chart_data,
        table_data=curve_table_data,
        available_dates=[d.strftime("%Y-%m-%d") for d in available_dates],
        selected_date=selected_date_str,
        num_prev_days=num_prev_days,
        color_palette=COLOR_PALETTE,
    )


@curve_bp.route("/govt_yield_curve")
def govt_yield_curve():
    """Display government bond yields against yield curves."""
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    import os
    
    try:
        data_folder = current_app.config.get("DATA_FOLDER")
        
        # Load data files
        sec_ytm_path = os.path.join(data_folder, "sec_YTM.csv")
        sec_ytmsp_path = os.path.join(data_folder, "sec_YTMSP.csv")  # New SP dataset
        curves_path = os.path.join(data_folder, "curves.csv")
        reference_path = os.path.join(data_folder, "reference.csv")
        
        # Read the data files
        sec_ytm_df = pd.read_csv(sec_ytm_path)
        sec_ytmsp_df = pd.read_csv(sec_ytmsp_path)
        curves_df = pd.read_csv(curves_path)
        reference_df = pd.read_csv(reference_path)
        
        # ---------------------------------------------------------------
        # Derive available dates using the same canonicalisation logic as
        # the API endpoint (handles DD/MM/YYYY vs YYYY-MM-DD).
        # ---------------------------------------------------------------

        date_col_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

        def build_date_lookup_view(columns):
            lookup = {}
            for col in columns:
                if date_col_pattern.match(str(col)) or '/' in str(col):
                    try:
                        # For YYYY-MM-DD format, don't use dayfirst=True
                        if date_col_pattern.match(str(col)):
                            canon = pd.to_datetime(col).strftime('%Y-%m-%d')
                        else:
                            # For DD/MM/YYYY format (with slashes), use dayfirst=True
                            canon = pd.to_datetime(col, dayfirst=True).strftime('%Y-%m-%d')
                        lookup.setdefault(canon, col)
                    except Exception:
                        continue
            return lookup

        date_lookup_view = build_date_lookup_view(sec_ytm_df.columns)

        available_dates = sorted(date_lookup_view.keys(), reverse=True)

        latest_date = available_dates[0] if available_dates else None

        current_app.logger.info(
            "govt_yield_curve view – total available dates: %d (latest: %s)",
            len(available_dates),
            latest_date,
        )

        # Get available currencies from curves data (filter out NaN values)
        available_currencies = sorted(curves_df['Currency Code'].dropna().unique().tolist())
        
        # Country options by currency – only include countries that have gov bonds with YTM data for that currency
        govt_df = reference_df[reference_df['Security Sub Type'] == 'Govt Bond']
        
        # Merge with YTM data to ensure we only show countries that have bonds with actual YTM data
        govt_with_ytm = pd.merge(
            govt_df,
            sec_ytm_df[['ISIN']],  # Only need ISIN column to check existence
            on='ISIN',
            how='inner'  # Only keep government bonds that have YTM data
        )
        
        current_app.logger.info(
            "Government bonds filtering: %d total govt bonds in reference, %d have YTM data available",
            len(govt_df),
            len(govt_with_ytm)
        )
        
        country_map = {}
        for ccy in available_currencies:
            # Filter by currency and get unique countries that have YTM data
            ccy_bonds = govt_with_ytm[govt_with_ytm['Position Currency'] == ccy]
            ctry_list = sorted(ccy_bonds['Country Of Risk'].dropna().unique().tolist())
            ctry_list.insert(0, 'All Countries')
            country_map[ccy] = ctry_list
            
            current_app.logger.debug(
                "Currency %s: %d govt bonds with YTM data, countries: %s",
                ccy,
                len(ccy_bonds),
                ctry_list[1:] if len(ctry_list) > 1 else []  # Exclude 'All Countries'
            )

        # Initial available countries (default currency 'USD' or first currency)
        default_currency = 'USD'
        initial_countries = country_map.get(default_currency, list(next(iter(country_map.values()))))

        # Get government securities from reference data (filtering by precise subtype)
        govt_securities = reference_df[reference_df['Security Sub Type'] == 'Govt Bond'].copy()

        current_app.logger.info(
            "Total 'Govt Bond' securities found: %d",
            len(govt_securities)
        )

        current_app.logger.info(f"Found {len(govt_securities)} government securities")
        current_app.logger.info(f"Available currencies: {available_currencies}")
        current_app.logger.info(f"Latest date: {latest_date}")
        
        return render_template(
            "govt_yield_curve.html",
            available_currencies=available_currencies,
            available_dates=available_dates,
            latest_date=latest_date,
            country_map=country_map,
            initial_countries=initial_countries,
            govt_securities_count=len(govt_securities)
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in govt_yield_curve: {e}", exc_info=True)
        return render_template("error.html", error_message=str(e))


@curve_bp.route("/curve/api/govt_yield_curve_data")
def api_govt_yield_curve_data():
    """API endpoint to get government bond yield curve data."""
    import pandas as pd
    import numpy as np
    from datetime import datetime
    import os
    
    try:
        # Get parameters
        currency = request.args.get('currency', 'USD')
        country = request.args.get('country', 'All Countries')
        date = request.args.get('date')
        
        data_folder = current_app.config.get("DATA_FOLDER")
        
        # Load data files
        sec_ytm_path = os.path.join(data_folder, "sec_YTM.csv")
        sec_ytmsp_path = os.path.join(data_folder, "sec_YTMSP.csv")  # New SP dataset
        curves_path = os.path.join(data_folder, "curves.csv")
        reference_path = os.path.join(data_folder, "reference.csv")
        
        sec_ytm_df = pd.read_csv(sec_ytm_path)
        sec_ytmsp_df = pd.read_csv(sec_ytmsp_path)
        curves_df = pd.read_csv(curves_path)
        reference_df = pd.read_csv(reference_path)
        
        # ------------------------------------------------------------------
        # Canonicalise date columns – handle both YYYY-MM-DD and DD/MM/YYYY.
        # Build mapping so we can transparently look up the right original
        # column name regardless of formatting.
        # ------------------------------------------------------------------

        date_col_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

        def build_date_lookup(columns):
            """Return dict mapping canonical YYYY-MM-DD → original column name."""
            lookup = {}
            for col in columns:
                if date_col_pattern.match(str(col)) or '/' in str(col):
                    try:
                        # For YYYY-MM-DD format, don't use dayfirst=True
                        if date_col_pattern.match(str(col)):
                            canon = pd.to_datetime(col).strftime('%Y-%m-%d')
                        else:
                            # For DD/MM/YYYY format (with slashes), use dayfirst=True
                            canon = pd.to_datetime(col, dayfirst=True).strftime('%Y-%m-%d')
                        # Only set first occurrence
                        lookup.setdefault(canon, col)
                    except Exception:
                        continue
            return lookup

        ytm_date_lookup = build_date_lookup(sec_ytm_df.columns)
        ytmsp_date_lookup = build_date_lookup(sec_ytmsp_df.columns)

        current_app.logger.info(
            "Date lookup built – sec_YTM keys: %d (earliest %s, latest %s), sec_YTMSP keys: %d",
            len(ytm_date_lookup),
            min(ytm_date_lookup.keys()) if ytm_date_lookup else "n/a",
            max(ytm_date_lookup.keys()) if ytm_date_lookup else "n/a",
            len(ytmsp_date_lookup)
        )

        # ------------------------------------------------------------------
        # Debug helper: pick the first bond in sec_YTM for the requested
        # currency (if available) and log whether this ISIN exists in each
        # dataset we join against. This helps trace data-mismatch issues in
        # production where no government bonds appear on the chart.
        # ------------------------------------------------------------------

        sample_isin = None
        if 'Currency' in sec_ytm_df.columns:
            usd_subset = sec_ytm_df[sec_ytm_df['Currency'] == currency]
            if not usd_subset.empty:
                sample_isin = usd_subset['ISIN'].iloc[0]

        # Fallback: take the first ISIN overall if currency-specific one not found
        if sample_isin is None and not sec_ytm_df.empty:
            sample_isin = sec_ytm_df['ISIN'].iloc[0]

        if sample_isin:
            presence_sec_ytm = not sec_ytm_df[sec_ytm_df['ISIN'] == sample_isin].empty
            presence_sec_ytmsp = not sec_ytmsp_df[sec_ytmsp_df['ISIN'] == sample_isin].empty
            presence_reference = not reference_df[reference_df['ISIN'] == sample_isin].empty

            current_app.logger.info(
                "Presence check for sample ISIN %s — sec_YTM:%s, sec_YTMSP:%s, reference:%s",
                sample_isin,
                presence_sec_ytm,
                presence_sec_ytmsp,
                presence_reference
            )

        # Filter for government bonds in the specified currency. We now match on
        # 'Govt Bond' rather than the previous, overly-broad 'Govt' subtype.
        govt_filter = (
            (reference_df['Security Sub Type'] == 'Govt Bond') &
            (reference_df['Position Currency'] == currency)
        )
        if country and country != 'All Countries':
            govt_filter &= (reference_df['Country Of Risk'] == country)

        govt_securities = reference_df[govt_filter].copy()

        current_app.logger.info(
            "Currency filter: %s – Govt bonds after currency filter: %d",
            currency,
            len(govt_securities)
        )

        # If nothing found, log some diagnostics
        if govt_securities.empty:
            available_currencies_govt = reference_df[reference_df['Security Sub Type'] == 'Govt Bond']['Position Currency'].unique().tolist()
            current_app.logger.warning(
                "No govt bonds found for currency %s. Available currencies containing govt bonds: %s",
                currency,
                available_currencies_govt
            )

        # Get curve data for the specified currency and date
        curves_df['Date'] = pd.to_datetime(curves_df['Date']).dt.strftime('%Y-%m-%d')
        curve_data = curves_df[
            (curves_df['Currency Code'] == currency) & 
            (curves_df['Date'] == date)
        ].copy()
        
        # Convert terms to months for plotting
        def term_to_months(term):
            """Convert term string to months."""
            if 'D' in term:
                return float(term.replace('D', '')) / 30.0  # Approximate days to months
            elif 'M' in term:
                return float(term.replace('M', ''))
            else:
                return 0
        
        curve_data['Months'] = curve_data['Term'].apply(term_to_months)
        curve_data = curve_data.sort_values('Months')
        
        # Calculate maturity in months for government securities
        # Assuming maturity date format is MM/DD/YYYY
        def calc_months_to_maturity(maturity_date_str, current_date_str):
            """Calculate months to maturity."""
            try:
                current_date = datetime.strptime(current_date_str, '%Y-%m-%d')
                # Handle various maturity date formats including Excel serial dates
                try:
                    # Import enhanced date parser that handles Excel serial dates
                    from synth_spread_calculator import parse_date_robust
                    maturity_parsed = parse_date_robust(maturity_date_str, dayfirst=False)
                    if pd.isna(maturity_parsed):
                        raise ValueError(f"Could not parse maturity date: {maturity_date_str}")
                    maturity_date = maturity_parsed.to_pydatetime()
                except Exception:
                    # Fallback to existing parsing logic
                    if '/' in maturity_date_str:
                        # Format like DD/MM/YYYY or MM/DD/YYYY – let pandas infer with dayfirst=False
                        maturity_date = pd.to_datetime(maturity_date_str, dayfirst=False).to_pydatetime()
                    else:
                        # Possible ISO format with 'T', e.g., '2025-07-01T00:00:00'
                        maturity_date_clean = maturity_date_str.split('T')[0]
                        maturity_date = datetime.strptime(maturity_date_clean, '%Y-%m-%d')
                
                delta = maturity_date - current_date
                return delta.days / 30.0  # Convert days to approximate months
            except:
                return None
        
        govt_securities['Months_To_Maturity'] = govt_securities['Maturity Date'].apply(
            lambda x: calc_months_to_maturity(x, date)
        )
        
        # Get YTM data for the specified date
        # Convert date format to match sec_YTM columns
        ytm_date_col = pd.to_datetime(date).strftime('%Y-%m-%d')
        
        # ---------------------------------------------------------------
        # Resolve original column name for requested date
        # ---------------------------------------------------------------

        orig_ytm_col = ytm_date_lookup.get(ytm_date_col)

        if orig_ytm_col is None:
            current_app.logger.warning(
                "Requested date column '%s' could not be resolved in sec_YTM. Available canonical keys (sample): %s",
                ytm_date_col,
                list(ytm_date_lookup.keys())[:10]
            )

        orig_ytmsp_col = ytmsp_date_lookup.get(ytm_date_col)

        current_app.logger.info(
            "Resolved original columns – sec_YTM:%s, sec_YTMSP:%s for requested date %s",
            orig_ytm_col,
            orig_ytmsp_col,
            ytm_date_col,
        )

        # ---------------------------------------------------------------
        # Merge government securities with YTM data
        # ---------------------------------------------------------------

        if orig_ytm_col is None:
            current_app.logger.warning(
                "Requested date column '%s' could not be resolved in sec_YTM. Available canonical keys (sample): %s",
                ytm_date_col,
                list(ytm_date_lookup.keys())[:10]
            )

        # Merge government securities with YTM data
        ytm_data = []
        # --- Counters for summary logging ---
        processed_count = 0
        matched_count = 0
        ytm_value_present = 0  # non-NaN regardless of maturity validity
        debug_examples = []  # Store first few examples for logging
        
        for _, govt_sec in govt_securities.iterrows():
            isin = govt_sec['ISIN']
            ytm_row = sec_ytm_df[sec_ytm_df['ISIN'] == isin]
            
            ytm_value = None
            if not ytm_row.empty and orig_ytm_col and orig_ytm_col in ytm_row.columns:
                ytm_value = ytm_row[orig_ytm_col].iloc[0]
                if pd.notna(ytm_value):
                    ytm_value_present += 1

                if pd.notna(ytm_value) and pd.notna(govt_sec['Months_To_Maturity']):
                    ytm_data.append({
                        'ISIN': isin,
                        'Security_Name': govt_sec['Security Name'],
                        'YTM': float(ytm_value),
                        'Months_To_Maturity': float(govt_sec['Months_To_Maturity']),
                        'Currency': govt_sec['Position Currency']
                    })
                    matched_count += 1

            processed_count += 1

            # Store first 3 examples for debugging
            if len(debug_examples) < 3:
                debug_examples.append({
                    'isin': isin,
                    'ytm_value': ytm_value if ytm_value is not None else 'n/a',
                    'months_to_maturity': govt_sec['Months_To_Maturity']
                })

        # Summary logging
        current_app.logger.info(
            "Processed %d govt bonds – YTM present: %d, matched with maturity: %d for date %s",
            processed_count,
            ytm_value_present,
            matched_count,
            ytm_date_col
        )
        
        # Log debug examples
        if debug_examples:
            current_app.logger.debug(f"Debug examples for {currency} bonds:")
            for example in debug_examples:
                current_app.logger.debug(
                    f"  - ISIN:{example['isin']}, YTM:{example['ytm_value']}, MonthsToMat:{example['months_to_maturity']}"
                )
        
        # --- Process sec_YTMSP.csv securities (other securities) ---
        # Join SP data with reference to pick up maturity, currency and subtype information
        sp_join_df = pd.merge(
            sec_ytmsp_df,
            reference_df[['ISIN', 'Maturity Date', 'Position Currency', 'Security Sub Type', 'Country Of Risk']],
            on='ISIN',
            how='left'
        )

        # Filter for the requested currency AND limit to government bonds only
        sp_filter = (
            (sp_join_df['Position Currency'] == currency) &
            (sp_join_df['Security Sub Type'] == 'Govt Bond')
        )
        if country and country != 'All Countries' and 'Country Of Risk' in sp_join_df.columns:
            sp_filter &= (sp_join_df['Country Of Risk'] == country)

        sp_join_df = sp_join_df[sp_filter].copy()

        current_app.logger.info(
            "SP join – rows after currency & subtype filter: %d",
            len(sp_join_df)
        )

        # Compute Months_To_Maturity for SP securities
        sp_join_df['Months_To_Maturity'] = sp_join_df['Maturity Date'].apply(
            lambda x: calc_months_to_maturity(x, date)
        )

        sp_bonds = []
        for _, sp_row in sp_join_df.iterrows():
            isin = sp_row['ISIN']
            if orig_ytmsp_col and orig_ytmsp_col in sp_row:
                ytm_value = sp_row[orig_ytmsp_col]
                if pd.notna(ytm_value) and pd.notna(sp_row['Months_To_Maturity']):
                    sp_bonds.append({
                        'ISIN': isin,
                        'Security_Name': sp_row['Security Name'],
                        'YTM': float(ytm_value),
                        'Months_To_Maturity': float(sp_row['Months_To_Maturity']),
                        'Currency': sp_row['Position Currency']
                    })
        
        # Prepare curve data for JSON
        curve_points = []
        for _, row in curve_data.iterrows():
            curve_points.append({
                'Term': row['Term'],
                'Months': float(row['Months']),
                'Yield': float(row['Daily Value'])
            })
        
        current_app.logger.info(
            f"Returning {len(ytm_data)} govt bonds, {len(sp_bonds)} SP bonds and {len(curve_points)} curve points"
        )
        
        return jsonify({
            'curve_data': curve_points,
            'govt_bonds': ytm_data,
            'sp_bonds': sp_bonds,
            'currency': currency,
            'date': date
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in api_govt_yield_curve_data: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
