"""
Defines the Flask routes for API data calls, including:
- Running API calls with simulation or real API calls
- Rerunning individual API queries
"""

import os
import pandas as pd
from flask import request, current_app, jsonify, Response
import datetime
import time
import json
from typing import Any, Dict, Optional, Tuple, List
import threading
import uuid
import csv
from collections import defaultdict

# Import from our local modules
from views.api_core import (
    api_bp,
    _simulate_and_print_tqs_call,
    _fetch_real_tqs_data,
    _find_key_columns,
    USE_REAL_TQS_API,
)

# Import the validation function from data_validation
from data_validation import validate_data
from utils import load_fund_groups

# --- In-memory job manager (job_id -> job dict) ---
job_manager = {}
job_manager_lock = threading.Lock()

# --- Times.csv helpers ---
TIMES_CSV = os.path.join('Data', 'Times.csv')
TIMES_HEADER = ['start_time', 'end_time', 'total_seconds', 'funds', 'dates', 'units', 'run_total_seconds', 'run_total_units']

def append_times_csv(start, end, funds, dates, units):
    """Append a run to Times.csv and update running totals."""
    total_seconds = (end - start).total_seconds()
    # Read current totals
    run_total_seconds, run_total_units = 0, 0
    if os.path.exists(TIMES_CSV):
        with open(TIMES_CSV, 'r', newline='') as f:
            rows = list(csv.DictReader(f))
            if rows:
                last = rows[-1]
                run_total_seconds = float(last.get('run_total_seconds', 0))
                run_total_units = int(last.get('run_total_units', 0))
    run_total_seconds += total_seconds
    run_total_units += units
    # Append new row
    write_header = not os.path.exists(TIMES_CSV)
    with open(TIMES_CSV, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=TIMES_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerow({
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'total_seconds': total_seconds,
            'funds': funds,
            'dates': dates,
            'units': units,
            'run_total_seconds': run_total_seconds,
            'run_total_units': run_total_units
        })

def estimate_time(funds, dates):
    """Estimate expected time for a run with given units."""
    if not os.path.exists(TIMES_CSV):
        return None
    with open(TIMES_CSV, 'r', newline='') as f:
        rows = list(csv.DictReader(f))
        if not rows:
            return None
        total_sec = float(rows[-1]['run_total_seconds'])
        total_units = int(rows[-1]['run_total_units'])
        if total_units == 0:
            return None
        avg_per_unit = total_sec / total_units
        return avg_per_unit * (funds * dates)

def _fetch_data_for_query(
    query_id: str, selected_funds: List[str], start_date: str, end_date: str
) -> Optional[pd.DataFrame]:
    """
    Fetches data for a given query using the real TQS API.
    Returns a DataFrame or None if the fetch fails.
    """
    try:
        return _fetch_real_tqs_data(query_id, selected_funds, start_date, end_date)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching data for QueryID {query_id}: {e}", exc_info=True
        )
        return None


def _validate_fetched_data(df: pd.DataFrame, file_name: str) -> str:
    """
    Validates the fetched DataFrame using the validate_data function.
    Returns a string status.
    """
    try:
        return validate_data(df, file_name)
    except Exception as e:
        current_app.logger.error(
            f"Error validating data for {file_name}: {e}", exc_info=True
        )
        return f"Validation Error: {e}"


def _save_or_merge_data(
    df_new: pd.DataFrame,
    output_path: str,
    file_type: str,
    force_overwrite: bool,
    summary: Dict[str, Any],
    file_name: str,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Handles saving or merging the new DataFrame with existing data, depending on file type and overwrite mode.
    Returns the DataFrame to save and the updated summary dict.
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_to_save = None
    if file_type == "ts":
        if force_overwrite:
            current_app.logger.info(
                f"[{file_name}] Overwrite Mode enabled. Skipping check for existing file."
            )
            if os.path.exists(output_path):
                summary["save_action"] = "Overwritten (User Request)"
            else:
                summary["save_action"] = "Created (Overwrite Mode)"
            df_to_save = df_new
        elif os.path.exists(output_path):
            current_app.logger.info(
                f"[{file_name}] TS file exists. Reading existing data for merge/append."
            )
            try:
                df_existing = pd.read_csv(output_path, low_memory=False)
                if not df_existing.empty and not df_new.empty:
                    date_col_new, fund_col_new = _find_key_columns(
                        df_new, f"{file_name} (New TS Data)"
                    )
                    date_col_existing, fund_col_existing = _find_key_columns(
                        df_existing, f"{file_name} (Existing TS)"
                    )
                    if (
                        date_col_existing == date_col_new
                        and fund_col_existing == fund_col_new
                    ):
                        date_col = date_col_new
                        fund_col = fund_col_new
                        df_existing[fund_col] = df_existing[fund_col].astype(str)
                        df_new[fund_col] = df_new[fund_col].astype(str)
                        funds_in_new_data = [str(f) for f in df_new[fund_col].unique()]
                        if (
                            date_col in df_existing.columns
                            and date_col in df_new.columns
                        ):
                            dates_in_new = df_new[date_col].astype(str).unique()
                            mask = ~(
                                (df_existing[fund_col].isin(funds_in_new_data))
                                & (df_existing[date_col].astype(str).isin(dates_in_new))
                            )
                            df_existing_filtered = df_existing[mask]
                        else:
                            df_existing_filtered = df_existing[
                                ~df_existing[fund_col].isin(funds_in_new_data)
                            ]
                        df_combined = pd.concat(
                            [df_existing_filtered, df_new], ignore_index=True
                        )
                        try:
                            df_combined = df_combined.sort_values(
                                by=[date_col, fund_col]
                            )
                        except Exception as sort_err:
                            current_app.logger.warning(
                                f"[{file_name}] Could not sort combined data: {sort_err}"
                            )
                        df_to_save = df_combined
                        summary["save_action"] = "Combined (Append/Overwrite)"
                        summary["last_written"] = now_str
                        current_app.logger.info(
                            f"[{file_name}] Prepared combined data ({len(df_to_save)} rows)."
                        )
                    else:
                        current_app.logger.warning(
                            f"[{file_name}] Key columns mismatch between existing ({date_col_existing}, {fund_col_existing}) and new ({date_col_new}, {fund_col_new}). Overwriting entire file."
                        )
                        summary["save_action"] = "Overwritten (Column Mismatch)"
                        summary["last_written"] = now_str
                        df_to_save = df_new
                else:
                    summary["save_action"] = "Overwritten (Merge Skipped)"
                    summary["last_written"] = now_str
                    df_to_save = df_new
            except Exception as read_err:
                current_app.logger.error(
                    f"[{file_name}] Error reading existing TS file: {read_err}. Overwriting.",
                    exc_info=True,
                )
                summary["save_action"] = "Overwritten (Read Error)"
                summary["last_written"] = now_str
                df_to_save = df_new
        else:
            current_app.logger.info(
                f"[{file_name}] TS file does not exist. Creating new file."
            )
            summary["save_action"] = "Created"
            summary["last_written"] = now_str
            df_to_save = df_new
    elif file_type == "pre":
        if os.path.exists(output_path):
            try:
                if not df_new.empty:
                    existing_header_df = pd.read_csv(
                        output_path, nrows=0, low_memory=False
                    )
                    existing_cols = existing_header_df.columns.tolist()
                    new_cols = df_new.columns.tolist()
                    if (
                        force_overwrite
                        or len(existing_cols) != len(new_cols)
                        or set(existing_cols) != set(new_cols)
                    ):
                        if force_overwrite:
                            summary["save_action"] = "Overwritten (User Request)"
                        else:
                            summary["save_action"] = "Overwritten (Column Mismatch)"
                    else:
                        summary["save_action"] = "Overwritten"
                else:
                    summary["save_action"] = "Overwritten (New Data Empty)"
            except pd.errors.EmptyDataError:
                summary["save_action"] = "Overwritten (Existing Empty)"
            except Exception as read_err:
                current_app.logger.error(
                    f"[{file_name}] Error reading existing pre_ file header: {read_err}. Overwriting.",
                    exc_info=True,
                )
                summary["save_action"] = "Overwritten (Read Error)"
        else:
            summary["save_action"] = "Created"
        df_to_save = df_new
    else:
        if os.path.exists(output_path):
            try:
                if not df_new.empty:
                    existing_header_df = pd.read_csv(
                        output_path, nrows=0, low_memory=False
                    )
                    existing_cols = existing_header_df.columns.tolist()
                    new_cols = df_new.columns.tolist()
                    if (
                        force_overwrite
                        or len(existing_cols) != len(new_cols)
                        or set(existing_cols) != set(new_cols)
                    ):
                        if force_overwrite:
                            summary["save_action"] = "Overwritten (User Request)"
                        else:
                            summary["save_action"] = "Overwritten (Column Mismatch)"
                    else:
                        summary["save_action"] = "Overwritten"
                else:
                    summary["save_action"] = "Overwritten (New Data Empty)"
            except pd.errors.EmptyDataError:
                summary["save_action"] = "Overwritten (Existing Empty)"
            except Exception as read_err:
                current_app.logger.error(
                    f"[{file_name}] Error reading existing 'other' file header: {read_err}. Overwriting.",
                    exc_info=True,
                )
                summary["save_action"] = "Overwritten (Read Error)"
        else:
            summary["save_action"] = "Created"
        df_to_save = df_new
    return df_to_save, summary


@api_bp.route("/run_api_calls", methods=["POST"])
def run_api_calls() -> Response:
    """Start a background API job, return job_id and estimated time."""
    data = request.get_json()
    funds_len = len(data.get('funds', []))
    if data.get('date_mode') == 'range':
        d0 = pd.to_datetime(data.get('start_date'))
        d1 = pd.to_datetime(data.get('custom_end_date'))
        dates_val = (d1 - d0).days + 1
    else:
        dates_val = int(data.get('days_back', 30)) + 1
    units_val = funds_len * dates_val
    est_time = estimate_time(funds_len, dates_val)
    
    actual_app = current_app._get_current_object()
    
    job_id = str(uuid.uuid4())
    with job_manager_lock:
        job_manager[job_id] = {
            'status': 'queued',
            'progress': 0,
            'total': 1,
            'result': None,
            'error': None
        }
    t = threading.Thread(target=run_api_job, args=(actual_app, job_id, data), daemon=True)
    t.start()
    return jsonify({'job_id': job_id, 'est_time': est_time})


@api_bp.route("/api/job_status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Return progress and result for a job."""
    with job_manager_lock:
        job = job_manager.get(job_id)
        if not job:
            return jsonify({'status': 'error', 'error': 'Job not found'}), 404
        resp = {
            'status': job['status'],
            'progress': job.get('progress', 0),
            'total': job.get('total', 1),
            'result': job.get('result'),
            'error': job.get('error')
        }
        return jsonify(resp)


@api_bp.route("/rerun-api-call", methods=["POST"])
def rerun_api_call() -> Response:
    """Handles the request to rerun a single API call (real or simulated)."""
    try:
        data = request.get_json()
        query_id = data.get("query_id")
        days_back = int(data.get("days_back", 30))
        end_date_str = data.get("end_date")
        selected_funds = data.get("funds", [])  # Get the list of funds
        overwrite_mode = data.get("overwrite_mode", False)  # Get the new overwrite flag

        # --- Basic Input Validation ---
        if not query_id:
            return jsonify({"status": "error", "message": "Query ID is required."}), 400
        if not end_date_str:
            return jsonify({"status": "error", "message": "End date is required."}), 400
        if not selected_funds:
            # Allow rerunning even if no funds are selected? Decide based on API behavior.
            # For now, let's require funds similar to the initial run.
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "At least one fund must be selected.",
                    }
                ),
                400,
            )

        # --- Calculate Dates ---
        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - pd.Timedelta(days=days_back)
        start_date_tqs_str = start_date.strftime("%Y-%m-%d")
        end_date_tqs_str = end_date.strftime("%Y-%m-%d")

        # --- Find FileName from QueryMap ---
        data_folder = current_app.config.get("DATA_FOLDER", "Data")
        query_map_path = os.path.join(data_folder, "QueryMap.csv")
        if not os.path.exists(query_map_path):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"QueryMap.csv not found at {query_map_path}",
                    }
                ),
                500,
            )

        query_map_df = pd.read_csv(query_map_path)
        # Ensure comparison is string vs string
        query_map_df["QueryID"] = query_map_df["QueryID"].astype(str)

        if (
            "QueryID" not in query_map_df.columns
            or "FileName" not in query_map_df.columns
        ):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "QueryMap.csv missing required columns (QueryID, FileName).",
                    }
                ),
                500,
            )

        # Compare string query_id from request with string QueryID column
        query_row = query_map_df[query_map_df["QueryID"] == query_id]
        if query_row.empty:
            # Log the types for debugging if it still fails
            current_app.logger.warning(
                f"QueryID '{query_id}' (type: {type(query_id)}) not found in QueryMap QueryIDs (types: {query_map_df['QueryID'].apply(type).unique()})."
            )
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"QueryID '{query_id}' not found in QueryMap.csv.",
                    }
                ),
                404,
            )

        file_name = query_row.iloc[0]["FileName"]
        output_path = os.path.join(data_folder, file_name)

        # --- Execute Single API Call (Simulated or Real) ---
        status = "Rerun Error: Unknown"
        rows_returned = 0
        lines_in_file = 0
        actual_df = None
        simulated_rows = None  # Initialize simulation keys too
        simulated_lines = None

        try:
            if USE_REAL_TQS_API:
                # --- Real API Call, Validation, and Save ---
                actual_df = _fetch_real_tqs_data(
                    query_id, selected_funds, start_date_tqs_str, end_date_tqs_str
                )

                if actual_df is not None and isinstance(actual_df, pd.DataFrame):
                    rows_returned = len(actual_df)
                    if actual_df.empty:
                        current_app.logger.info(
                            f"(Rerun) API returned empty DataFrame for {query_id} ({file_name}). Saving empty file."
                        )
                        status = "Saved OK (Empty)"
                    else:
                        is_valid, validation_errors = validate_data(
                            actual_df, file_name
                        )
                        if not is_valid:
                            current_app.logger.warning(
                                f"(Rerun) Data validation failed for {file_name}: {validation_errors}"
                            )
                            status = (
                                f"Validation Failed: {'; '.join(validation_errors)}"
                            )
                            lines_in_file = 0
                        # else: Validation passed

                    if not status.startswith("Validation Failed"):
                        try:
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            actual_df.to_csv(output_path, index=False)
                            current_app.logger.info(
                                f"(Rerun) Successfully saved data to {output_path}"
                            )
                            lines_in_file = rows_returned + 1
                            if status != "Saved OK (Empty)":
                                status = "Saved OK"
                        except Exception as e:
                            current_app.logger.error(
                                f"(Rerun) Error saving DataFrame to {output_path}: {e}",
                                exc_info=True,
                            )
                            status = f"Save Error: {e}"
                            lines_in_file = 0

                elif actual_df is None:
                    current_app.logger.warning(
                        f"(Rerun) Real API call/fetch for {query_id} ({file_name}) returned None."
                    )
                    status = "No Data / API Error / TQS Missing"
                    rows_returned = 0
                    lines_in_file = 0
                else:
                    current_app.logger.error(
                        f"(Rerun) Real API fetch for {query_id} ({file_name}) returned unexpected type: {type(actual_df)}."
                    )
                    status = "API Returned Invalid Type"
                    rows_returned = 0
                    lines_in_file = 0
            else:
                # --- Simulate API Call ---
                simulated_rows = _simulate_and_print_tqs_call(
                    query_id, selected_funds, start_date_tqs_str, end_date_tqs_str
                )
                rows_returned = simulated_rows
                lines_in_file = simulated_rows + 1 if simulated_rows > 0 else 0
                status = "Simulated OK"

        except Exception as e:
            current_app.logger.error(
                f"Error during single rerun for query {query_id} ({file_name}): {e}",
                exc_info=True,
            )
            status = f"Processing Error: {e}"
            rows_returned = 0
            lines_in_file = 0

        # --- Return Result for the Single Query ---
        result_data = {
            "status": status,
            # Provide consistent keys for the frontend to update the table
            "simulated_rows": simulated_rows,  # Value if simulated, None otherwise
            "actual_rows": (
                rows_returned if USE_REAL_TQS_API else None
            ),  # Value if real, None otherwise
            "simulated_lines": simulated_lines,  # Value if simulated, None otherwise
            "actual_lines": (
                lines_in_file if USE_REAL_TQS_API else None
            ),  # Value if real, None otherwise
        }

        return jsonify(result_data)

    except ValueError as ve:
        current_app.logger.error(f"Value error in /rerun-api-call: {ve}", exc_info=True)
        return (
            jsonify({"status": "error", "message": f"Invalid input value: {ve}"}),
            400,
        )
    except FileNotFoundError as fnf:
        current_app.logger.error(
            f"File not found error in /rerun-api-call: {fnf}", exc_info=True
        )
        return (
            jsonify({"status": "error", "message": f"Required file not found: {fnf}"}),
            500,
        )
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error in /rerun-api-call: {e}", exc_info=True
        )
        return (
            jsonify(
                {"status": "error", "message": f"An unexpected error occurred: {e}"}
            ),
            500,
        )


def get_schedules_file() -> str:
    return os.path.join(current_app.instance_path, "schedules.json")


def load_schedules() -> List[Any]:
    file = get_schedules_file()
    if not os.path.exists(file):
        return []
    try:
        with open(file, "r") as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error loading schedules: {e}", exc_info=True)
        return []


def save_schedules(schedules: List[Any]) -> None:
    file = get_schedules_file()
    try:
        with open(file, "w") as f:
            json.dump(schedules, f)
    except Exception as e:
        current_app.logger.error(f"Error saving schedules: {e}", exc_info=True)


@api_bp.route("/schedules", methods=["GET"])
def list_schedules() -> Response:
    return jsonify(load_schedules())


@api_bp.route("/schedules", methods=["POST"])
def add_schedule() -> Tuple[Response, int]:
    data = request.get_json() or {}
    schedule_time = data.get("schedule_time")
    write_mode = data.get("write_mode")
    date_mode = data.get("date_mode")
    funds = data.get("funds")
    fund_group = data.get("fund_group")  # Optionally sent from frontend in the future
    if (
        not schedule_time
        or not write_mode
        or not date_mode
        or not isinstance(funds, list)
        or not funds
    ):
        return jsonify({"message": "Missing or invalid schedule fields"}), 400
    if date_mode == "quick":
        days_back = data.get("days_back")
        if days_back is None:
            return jsonify({"message": "days_back is required for quick mode"}), 400
    else:
        start_offset = data.get("start_offset")
        end_offset = data.get("end_offset")
        if start_offset is None or end_offset is None:
            return (
                jsonify(
                    {
                        "message": "start_offset and end_offset are required for range mode"
                    }
                ),
                400,
            )
    # --- Fund group detection: if funds match a group exactly, save the group name ---
    data_folder = current_app.config.get("DATA_FOLDER", "Data")
    fund_groups = load_fund_groups(data_folder)
    matched_group = None
    for group_name, group_funds in fund_groups.items():
        if set(funds) == set(group_funds):
            matched_group = group_name
            break
    schedules = load_schedules()
    new_id = max((s["id"] for s in schedules), default=0) + 1
    sched = {
        "id": new_id,
        "schedule_time": schedule_time,
        "write_mode": write_mode,
        "date_mode": date_mode,
        "funds": funds,
    }
    if matched_group:
        sched["fund_group"] = matched_group
    if date_mode == "quick":
        sched["days_back"] = int(days_back)
    else:
        sched["start_offset"] = int(start_offset)
        sched["end_offset"] = int(end_offset)
    save_schedules(schedules + [sched])
    return jsonify(sched), 201


@api_bp.route("/schedules/<int:schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id: int) -> Tuple[str, int]:
    schedules = load_schedules()
    new_list = [s for s in schedules if s["id"] != schedule_id]
    if len(new_list) == len(schedules):
        return jsonify({"message": "Schedule not found"}), 404
    save_schedules(new_list)
    return "", 204


def run_scheduled_job(schedule: Dict[str, Any]) -> None:
    with current_app.app_context():
        payload = {
            "date_mode": schedule["date_mode"],
            "write_mode": schedule["write_mode"],
        }
        # --- Resolve funds from group if present ---
        data_folder = current_app.config.get("DATA_FOLDER", "Data")
        if "fund_group" in schedule:
            fund_groups = load_fund_groups(data_folder)
            funds = fund_groups.get(schedule["fund_group"], [])
            payload["funds"] = funds
        else:
            payload["funds"] = schedule["funds"]
        # ... existing date logic ...
        # (rest of the function unchanged)


# --- Background job worker ---
def run_api_job(app, job_id, params):
    """Worker function for API job. Updates job_manager with progress/results. Must run in Flask app context."""
    # Flask contexts are thread-local; we must push an app context in this thread.
    with app.app_context():
        with job_manager_lock:
            job = job_manager[job_id]
            job['status'] = 'running'
            job['progress'] = 0
            job['result'] = None
            job['error'] = None
        start = datetime.datetime.now()
        try:
            # --- Calculate units ---
            funds = len(params['funds'])
            if params['date_mode'] == 'range':
                d0 = pd.to_datetime(params['start_date'])
                d1 = pd.to_datetime(params['custom_end_date'])
                dates = (d1 - d0).days + 1
            else:
                dates = int(params['days_back']) + 1
            units = funds * dates
            # --- Get Query Map ---
            data_folder = app.config.get("DATA_FOLDER", "Data")
            query_map_path = os.path.join(data_folder, "QueryMap.csv")
            if not os.path.exists(query_map_path):
                raise FileNotFoundError(f"QueryMap.csv not found at {query_map_path}")
            query_map_df = pd.read_csv(query_map_path)
            if not {"QueryID", "FileName"}.issubset(query_map_df.columns):
                raise ValueError("QueryMap.csv missing required columns (QueryID, FileName)")
            
            def sort_key_with_index(item):
                index, query = item
                filename = query.get("FileName", "").lower()
                if filename.startswith("ts_"):
                    return (0, index)
                elif filename.startswith("pre_"):
                    return (1, index)
                else:
                    return (2, index)
            queries_with_indices = list(enumerate(query_map_df.to_dict("records")))
            queries_with_indices.sort(key=sort_key_with_index)
            queries = [item[1] for item in queries_with_indices]
            results_summary = []
            total = len(queries)
            completed = 0
            all_ts_files_succeeded = True
            overwrite_mode = params.get('write_mode', 'expand') == 'overwrite_all'
            
            if params['date_mode'] == 'range':
                start_date_tqs_str = params['start_date']
                end_date_tqs_str = params['custom_end_date']
            else:
                end_date_dt = pd.to_datetime(params['end_date']) # Ensure it's datetime
                start_date_dt = end_date_dt - pd.Timedelta(days=int(params['days_back']))
                start_date_tqs_str = start_date_dt.strftime("%Y-%m-%d")
                end_date_tqs_str = end_date_dt.strftime("%Y-%m-%d")
            selected_funds = params['funds']

            for query_info in queries:
                query_id = query_info.get("QueryID")
                file_name = query_info.get("FileName")
                summary = {
                    "query_id": query_id,
                    "file_name": file_name,
                    "status": "Pending",
                    "simulated_rows": None, "simulated_lines": None,
                    "actual_rows": None, "actual_lines": None,
                    "save_action": "N/A", "validation_status": "Not Run", "last_written": None,
                }
                file_type = "other"
                if file_name and file_name.lower().startswith("ts_"): file_type = "ts"
                elif file_name and file_name.lower().startswith("pre_"): file_type = "pre"
                
                try:
                    if not query_id or not file_name:
                        summary["status"] = "Skipped (Missing QueryID/FileName)"
                        summary["validation_status"] = "Not Run"
                        summary["save_action"] = "Skipped"
                        results_summary.append(summary)
                        completed += 1
                        with job_manager_lock:
                            job_manager[job_id]['progress'] = completed
                            job_manager[job_id]['total'] = total
                        continue
                    output_path = os.path.join(data_folder, file_name)
                    if file_type == "pre" and not all_ts_files_succeeded:
                        summary["status"] = "Skipped (Previous TS Failure)"
                        summary["validation_status"] = "Not Run"
                        summary["save_action"] = "Skipped"
                        results_summary.append(summary)
                        completed += 1
                        with job_manager_lock:
                            job_manager[job_id]['progress'] = completed
                            job_manager[job_id]['total'] = total
                        continue
                    
                    if USE_REAL_TQS_API:
                        df_new = None
                        df_to_save = None
                        force_overwrite = overwrite_mode
                        try:
                            df_new = _fetch_data_for_query(
                                query_id, selected_funds, start_date_tqs_str, end_date_tqs_str
                            )
                            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            if df_new is None:
                                summary["status"] = "Warning - No data returned from API"
                                summary["validation_status"] = "Skipped (API Returned None)"
                                summary["last_written"] = now_str
                                if file_type == "ts": all_ts_files_succeeded = False
                            elif df_new.empty:
                                summary["status"] = "Warning - Empty data returned from API"
                                summary["validation_status"] = "OK (Empty Data)"
                                df_to_save = df_new
                                summary["actual_rows"] = 0
                                summary["last_written"] = now_str
                            else:
                                summary["actual_rows"] = len(df_new)
                                df_to_save = df_new
                                summary["last_written"] = now_str
                            
                            if df_new is not None:
                                if file_type == "ts" and not df_new.empty:
                                    date_col_new, fund_col_new = _find_key_columns(
                                        df_new, f"{file_name} (New TS Data)"
                                    )
                                    if not date_col_new or not fund_col_new:
                                        raise ValueError(f"Could not find essential date/fund columns in fetched ts_ data for {file_name}.")
                                df_to_save, summary = _save_or_merge_data(
                                    df_new, output_path, file_type, force_overwrite, summary, file_name
                                )
                                if df_to_save is not None:
                                    try:
                                        df_to_save.to_csv(output_path, index=False, header=True)
                                        summary["status"] = "OK - Data Saved"
                                        try:
                                            with open(output_path, "r", encoding="utf-8") as f:
                                                summary["actual_lines"] = sum(1 for line in f)
                                        except Exception:
                                            summary["actual_lines"] = "N/A"
                                        summary["validation_status"] = _validate_fetched_data(df_to_save, file_name)
                                    except Exception as write_err:
                                        summary["status"] = f"Error - Failed to save file: {write_err}"
                                        summary["validation_status"] = "Failed (Save Error)"
                                        if file_type == "ts": all_ts_files_succeeded = False
                        except Exception as proc_err:
                            summary["status"] = f"Error - Processing failed: {proc_err}"
                            summary["validation_status"] = "Failed (Processing Error)"
                            summary["last_written"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            if file_type == "ts": all_ts_files_succeeded = False
                    else: # Simulation Mode
                        simulated_rows = _simulate_and_print_tqs_call(
                            query_id, selected_funds, start_date_tqs_str, end_date_tqs_str
                        )
                        summary["simulated_rows"] = simulated_rows
                        summary["simulated_lines"] = (simulated_rows + 1 if simulated_rows > 0 else 0)
                        summary["status"] = "Simulated OK"
                        summary["save_action"] = "Not Applicable"
                        summary["validation_status"] = "Not Run (Simulated)"
                        summary["last_written"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                except Exception as outer_err:
                    summary["status"] = f"Outer Processing Error: {outer_err}"
                    if file_type == "ts": all_ts_files_succeeded = False
                    summary["last_written"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                results_summary.append(summary)
                completed += 1
                with job_manager_lock:
                    job_manager[job_id]['progress'] = completed
                    job_manager[job_id]['total'] = total
                if USE_REAL_TQS_API and completed < total: time.sleep(3)
            
            end = datetime.datetime.now()
            append_times_csv(start, end, funds, dates, units)
            with job_manager_lock:
                job_manager[job_id]['status'] = 'done'
                job_manager[job_id]['result'] = {
                    'summary': results_summary,
                    'message': f'Processed {completed}/{total} API calls.',
                }
        except Exception as e:
            app.logger.error(f"Error in background job {job_id}: {e}", exc_info=True)
            with job_manager_lock:
                job_manager[job_id]['status'] = 'error'
                job_manager[job_id]['error'] = str(e)
