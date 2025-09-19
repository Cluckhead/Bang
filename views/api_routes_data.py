"""
Defines the Flask route for data retrieval interface and related functionality.
"""

import os
import pandas as pd
from flask import render_template, request, current_app, jsonify, Response
import datetime
from pandas.tseries.offsets import BDay
from typing import Union, Tuple
import sqlite3
import json

# Import from our local modules
from views.api_core import api_bp, get_data_file_statuses
from core.utils import load_fund_groups, time_api_calls  # Import the fund group loader and timing decorator
from data_processing.data_audit import run_data_consistency_audit  # Import the audit function


@api_bp.route("/get_data")
@time_api_calls
def get_data_page() -> Union[str, Tuple[str, int], Response]:
    """Renders the page for users to select parameters for API data retrieval."""
    try:
        # Construct the path to FundList.csv relative to the app's instance path or root
        # Assuming DATA_FOLDER is configured relative to the app root
        data_folder = current_app.config["DATA_FOLDER"]
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
@time_api_calls
def get_data_audit():
    """
    API endpoint to run the Data Consistency Audit and return the report as JSON.
    This is triggered by the button on the /get_data page.
    """
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        report = run_data_consistency_audit(data_folder)
        return jsonify({"success": True, "report": report})
    except Exception as e:
        current_app.logger.error(
            f"Error running data consistency audit: {e}", exc_info=True
        )
        return jsonify({"success": False, "error": str(e)})


@api_bp.route("/get_data/fetch_schedule_sql", methods=["POST"])
@time_api_calls
def fetch_schedule_from_sql() -> Response:
    """
    Runs a SQL query (from sql/schedule_query.sql) to export schedule data to Data/schedule.csv.
    Supports db_type: "mssql" (via pyodbc) or "sqlite" (via sqlite3). If no database
    details are provided or the query returns no rows, writes a sample CSV with the
    correct schema.

    Expected columns (in order):
    ISIN, CRD ID, Day Basis, First Coupon, Maturity Date, Accrued Interest, Issue Date, Call Schedule, Coupon Frequency
    """
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        output_path = os.path.join(data_folder, "schedule.csv")
        # Optional inputs
        payload = request.get_json(silent=True) or {}
        db_type = (payload.get("db_type") or "sqlite").lower()
        sqlite_path = payload.get("sqlite_path")  # Optional path to a SQLite DB file
        connection_string = payload.get("connection_string")  # For MSSQL
        mssql = payload.get("mssql", {})  # Optional dict with server, database, uid, pwd, driver, trusted

        # Load SQL text
        sql_path = os.path.join(current_app.root_path, "sql", "schedule_query.sql")
        if not os.path.exists(sql_path):
            return jsonify({"status": "error", "message": f"SQL file not found at {sql_path}"}), 500
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_text = f.read()

        # Execute query if we have a usable connection; otherwise, fall back to sample data
        df = None
        if db_type == "sqlite" and sqlite_path and os.path.exists(sqlite_path):
            try:
                with sqlite3.connect(sqlite_path) as conn:
                    df = pd.read_sql_query(sql_text, conn)
            except Exception as db_err:
                current_app.logger.warning(f"SQLite execution failed: {db_err}. Falling back to sample data.")
        elif db_type in ("mssql", "sqlserver", "sql_server"):
            try:
                try:
                    import pyodbc  # type: ignore
                except Exception as imp_err:
                    return jsonify({
                        "status": "error",
                        "message": f"pyodbc not available: {imp_err}. Install a SQL Server ODBC driver and pyodbc.",
                    }), 500

                if not connection_string:
                    server = mssql.get("server")
                    database = mssql.get("database")
                    uid = mssql.get("uid")
                    pwd = mssql.get("pwd")
                    driver = mssql.get("driver") or "ODBC Driver 18 for SQL Server"
                    trusted = mssql.get("trusted", True)
                    if not server or not database:
                        return jsonify({
                            "status": "error",
                            "message": "Missing SQL Server connection details. Provide connection_string or mssql.server/database.",
                        }), 400
                    if trusted:
                        connection_string = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=Yes;Encrypt=No"
                    else:
                        if not uid or not pwd:
                            return jsonify({
                                "status": "error",
                                "message": "Missing uid/pwd for SQL authentication.",
                            }), 400
                        connection_string = (
                            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};Encrypt=No"
                        )

                with pyodbc.connect(connection_string) as conn:
                    df = pd.read_sql(sql_text, conn)
            except Exception as db_err:
                current_app.logger.warning(f"MSSQL execution failed: {db_err}. Falling back to sample data.")

        # Build sample data if needed (or if query returned empty)
        if df is None or df.empty:
            # Minimal sample rows; replace later when real SQL/DB is provided
            sample_rows = [
                {
                    "ISIN": "US0000000001",
                    "CRD ID": 12345678,
                    "Day Basis": "30E/360",
                    "First Coupon": "21/09/2006",
                    "Maturity Date": "01/07/2025",
                    "Accrued Interest": 1.23456,
                    "Issue Date": "25/03/2006",
                    "Call Schedule": "[]",
                    "Coupon Frequency": 2,
                },
            ]
            df = pd.DataFrame(sample_rows)

        # Ensure exact column order and formatting
        expected_cols = [
            "ISIN",
            "CRD ID",
            "Day Basis",
            "First Coupon",
            "Maturity Date",
            "Accrued Interest",
            "Issue Date",
            "Call Schedule",
            "Coupon Frequency",
        ]
        # Add any missing columns with empty values, then reorder
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        df = df[expected_cols]

        # Format UK dates for the three date columns
        def _fmt_uk_date(series: pd.Series) -> pd.Series:
            parsed = pd.to_datetime(series, errors="coerce")
            out = series.astype(str)
            mask = parsed.notna()
            out.loc[mask] = parsed[mask].dt.strftime("%d/%m/%Y")
            return out

        for date_col in ["First Coupon", "Maturity Date", "Issue Date"]:
            df[date_col] = _fmt_uk_date(df[date_col])

        # Numeric formatting
        df["Accrued Interest"] = pd.to_numeric(df["Accrued Interest"], errors="coerce").round(5)
        df["Coupon Frequency"] = pd.to_numeric(df["Coupon Frequency"], errors="coerce").fillna(0).astype(int)

        # Ensure Call Schedule is string (if arrays/objects returned)
        def _to_str(v):
            try:
                return v if isinstance(v, str) else json.dumps(v)
            except Exception:
                return str(v)
        df["Call Schedule"] = df["Call Schedule"].apply(_to_str)

        # Write CSV
        os.makedirs(data_folder, exist_ok=True)
        df.to_csv(output_path, index=False)
        return jsonify({
            "status": "success",
            "message": "schedule.csv written",
            "rows_written": int(len(df)),
            "output_path": output_path,
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error exporting schedule from SQL: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
