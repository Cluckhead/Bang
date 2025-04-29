"""
Defines the Flask route for data retrieval interface and related functionality.
"""

import os
import pandas as pd
from flask import render_template, request, current_app, jsonify, Response
import datetime
from pandas.tseries.offsets import BDay
import typing

# Import from our local modules
from views.api_core import api_bp, get_data_file_statuses
from utils import load_fund_groups  # Import the fund group loader
from data_audit import run_data_consistency_audit  # Import the audit function


@api_bp.route("/get_data")
def get_data_page() -> typing.Union[str, typing.Tuple[str, int], Response]:
    """Renders the page for users to select parameters for API data retrieval."""
    try:
        # Construct the path to FundList.csv relative to the app's instance path or root
        # Assuming DATA_FOLDER is configured relative to the app root
        data_folder = current_app.config.get("DATA_FOLDER", "Data")
        fund_list_path = os.path.join(data_folder, "FundList.csv")

        if not os.path.exists(fund_list_path):
            current_app.logger.error(f"FundList.csv not found at {fund_list_path}")
            return "Error: FundList.csv not found.", 500

        fund_df = pd.read_csv(fund_list_path)

        # Ensure required columns exist
        if not {"Fund Code", "Total Asset Value USD", "Picked"}.issubset(
            fund_df.columns
        ):
            current_app.logger.error(f"FundList.csv is missing required columns.")
            return (
                "Error: FundList.csv is missing required columns (Fund Code, Total Asset Value USD, Picked).",
                500,
            )

        # Convert Total Asset Value to numeric, coercing errors
        fund_df["Total Asset Value USD"] = pd.to_numeric(
            fund_df["Total Asset Value USD"], errors="coerce"
        )
        fund_df.dropna(
            subset=["Total Asset Value USD"], inplace=True
        )  # Remove rows where conversion failed

        # Sort by Total Asset Value USD descending
        fund_df = fund_df.sort_values(by="Total Asset Value USD", ascending=False)

        # Convert Picked to boolean
        fund_df["Picked"] = fund_df["Picked"].astype(bool)

        # Prepare fund data for the template
        funds = fund_df.to_dict("records")

        # Calculate default end date (previous business day)
        default_end_date = (datetime.datetime.today() - BDay(1)).strftime("%Y-%m-%d")

        # --- Get Data File Statuses ---
        data_file_statuses = get_data_file_statuses(data_folder)
        # --- End Get Data File Statuses ---

        # --- Load Fund Groups for Dropdown ---
        fund_groups = load_fund_groups(
            data_folder
        )  # Always pass fund_groups to template
        selected_fund_group = (
            None  # Default to None; update if you add group selection logic
        )
        # --- End Fund Groups ---

    except Exception as e:
        current_app.logger.error(f"Error preparing get_data page: {e}", exc_info=True)
        # Provide a user-friendly error message, specific details are logged
        return f"An error occurred while preparing the data retrieval page: {e}", 500

    # Pass fund_groups and selected_fund_group to the template to avoid Undefined errors
    return render_template(
        "get_data.html",
        funds=funds,
        default_end_date=default_end_date,
        data_file_statuses=data_file_statuses,
        fund_groups=fund_groups,
        selected_fund_group=selected_fund_group,
    )


@api_bp.route("/get_data/audit")
def get_data_audit():
    """
    API endpoint to run the Data Consistency Audit and return the report as JSON.
    This is triggered by the button on the /get_data page.
    """
    try:
        data_folder = current_app.config.get("DATA_FOLDER", "Data")
        report = run_data_consistency_audit(data_folder)
        return jsonify({"success": True, "report": report})
    except Exception as e:
        current_app.logger.error(
            f"Error running data consistency audit: {e}", exc_info=True
        )
        return jsonify({"success": False, "error": str(e)})
