# Purpose: Defines the Flask Blueprint for yield curve analysis views.

# Stdlib imports
from datetime import datetime

# Third-party imports
from flask import Blueprint, render_template, request, jsonify, current_app
import pandas as pd
import numpy as np

# Local imports
from curve_processing import (
    load_curve_data,
    check_curve_inconsistencies,
    get_latest_curve_date,
)
from config import COLOR_PALETTE

curve_bp = Blueprint("curve_bp", __name__, template_folder="../templates")

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
