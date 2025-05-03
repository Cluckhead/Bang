# Purpose: This file defines the Flask Blueprint and routes for the "Inspect" feature – calculating security contributions and rendering the Inspect results pages.
# The Blueprint is separated from views/metric_views.py to keep metric-chart routes and contribution-analysis logic isolated for better maintainability.

from flask import Blueprint, jsonify, current_app, request, render_template
import os
import pandas as pd
import numpy as np
import math

from data_loader import load_simple_csv  # Re-use existing helper

# Re-declare make_json_safe locally to avoid circular imports with metric_views.py

def make_json_safe(obj):
    """Convert Pandas / NumPy / Python objects into JSON-serialisable primitives."""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj

# Blueprint dedicated to the Inspect feature.  We keep the same URL structure as before
# by re-using the "/metric" prefix.
inspect_bp = Blueprint("inspect", __name__, url_prefix="/metric")

# ---------------------------------------------------------------------------
# Helper Functions (moved from metric_views for isolation)
# ---------------------------------------------------------------------------

def _melt_data(df, id_vars, fund_code):
    """Convert wide security-level CSVs to a long format filtered by *fund_code*."""

    if df is None or df.empty:
        current_app.logger.warning(
            f"[_melt_data] Input DataFrame is None or empty for fund '{fund_code}'."
        )
        return None

    # ------------------------------------------------------------------
    # Filter by fund code – supports both scalar and list-encoded entries
    # in the *Funds* column (e.g. "[IG01, IG02]")
    # ------------------------------------------------------------------
    if "Funds" not in df.columns:
        current_app.logger.error(
            f"[_melt_data] 'Funds' column missing in DataFrame for fund '{fund_code}'."
        )
        return None

    def _fund_matches(entry, tgt):
        if pd.isna(entry):
            return False
        if isinstance(entry, str) and entry.startswith("[") and entry.endswith("]"):
            items = [i.strip().strip("'\"") for i in entry[1:-1].split(",") if i]
            return tgt in items
        return str(entry).strip() == tgt

    mask = df["Funds"].apply(lambda x: _fund_matches(x, fund_code))
    df_filtered = df[mask]

    if df_filtered.empty:
        current_app.logger.warning(
            f"[_melt_data] No rows for fund '{fund_code}' after filtering."
        )
        return pd.DataFrame(columns=id_vars + ["Date", "Value"])

    # Identify date columns
    date_cols = []
    for col in df_filtered.columns:
        if col in id_vars:
            continue
        try:
            pd.to_datetime(col, errors="raise")
            date_cols.append(col)
        except (ValueError, TypeError):
            continue

    if not date_cols:
        current_app.logger.error("[_melt_data] Could not detect any date columns.")
        return None

    melted_df = df_filtered.melt(
        id_vars=id_vars,
        value_vars=date_cols,
        var_name="Date",
        value_name="Value",
    )
    melted_df["Date"] = pd.to_datetime(melted_df["Date"], errors="coerce")
    return melted_df.dropna(subset=["Date"])


def _calculate_contributions(metric_name, fund_code, start_date_str, end_date_str, data_source, top_n=10):
    """Core calculation logic extracted from *metric_views*.

    Returns a JSON-serialisable dict with contributor/detractor tables or
    raises on failure (handled by view functions).
    """

    current_app.logger.info(
        f"--- Calculating Contributions for {metric_name} ({fund_code}) [{start_date_str} - {end_date_str}], Source: {data_source} ---"
    )

    # ----------------------- Validation & Parsing -----------------------
    if not all([start_date_str, end_date_str, fund_code, metric_name]):
        raise ValueError("Missing required parameters for calculation.")

    start_date = pd.to_datetime(start_date_str, errors="coerce")
    end_date = pd.to_datetime(end_date_str, errors="coerce")
    if pd.isna(start_date) or pd.isna(end_date):
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")
    if start_date >= end_date:
        raise ValueError("Start date must precede end date.")

    baseline_date = start_date - pd.Timedelta(days=1)

    data_folder = current_app.config["DATA_FOLDER"]
    weights_filename = "w_secs.csv"
    metric_filename = (
        f"sec_{metric_name}.csv" if data_source == "Original" else f"sec_{metric_name}SP.csv"
    )
    reference_filename = "reference.csv"

    # ----------------------------- Load CSVs ----------------------------
    weights_df_raw = load_simple_csv(os.path.join(data_folder, weights_filename), weights_filename)
    metric_df_raw = load_simple_csv(os.path.join(data_folder, metric_filename), metric_filename)

    if weights_df_raw is None:
        raise FileNotFoundError(f"Could not load {weights_filename}")
    if metric_df_raw is None:
        raise FileNotFoundError(f"Could not load {metric_filename}")

    weight_id = ["ISIN", "Funds"]
    metric_id = ["ISIN", "Funds"]

    weights_long = _melt_data(weights_df_raw, weight_id, fund_code)
    metric_long = _melt_data(metric_df_raw, metric_id, fund_code)

    if weights_long is None or weights_long.empty:
        raise ValueError("No weight data after processing.")
    if metric_long is None or metric_long.empty:
        raise ValueError("No metric data after processing.")

    weights_long.rename(columns={"Value": "Weight"}, inplace=True)
    metric_long.rename(columns={"Value": "MetricValue"}, inplace=True)

    weights_long["Weight"] = pd.to_numeric(weights_long["Weight"], errors="coerce")
    metric_long["MetricValue"] = pd.to_numeric(metric_long["MetricValue"], errors="coerce")

    weights_long.sort_values(["ISIN", "Date"], inplace=True)
    weights_long["Weight"] = weights_long.groupby("ISIN")["Weight"].ffill()

    merged = pd.merge(
        metric_long.dropna(subset=["MetricValue"]),
        weights_long.dropna(subset=["Weight"]),
        on=["ISIN", "Date"],
        how="inner",
    )
    if merged.empty:
        raise ValueError("No overlapping weight & metric rows.")

    merged["DailyContribution"] = merged["Weight"] * merged["MetricValue"]

    baseline = merged[merged["Date"] == baseline_date]
    baseline_contrib = (
        baseline.drop_duplicates("ISIN", keep="last")
        .set_index("ISIN")["DailyContribution"]
    )

    period = merged[(merged["Date"] >= start_date) & (merged["Date"] <= end_date)]
    if period.empty:
        raise ValueError("No data within selected period.")

    avg_contrib = period.groupby("ISIN")["DailyContribution"].mean()

    results = pd.DataFrame(avg_contrib).rename(columns={"DailyContribution": "AverageContribution"})
    results["BaselineContribution"] = results.index.map(baseline_contrib)

    results.dropna(subset=["BaselineContribution"], inplace=True)
    if results.empty:
        raise ValueError("No securities with baseline data available.")

    results["ContributionDifference"] = results["AverageContribution"] - results["BaselineContribution"]
    results = results[results["ContributionDifference"] != 0]

    # ------------------------- Merge Security Names ---------------------
    try:
        ref_df = load_simple_csv(os.path.join(data_folder, reference_filename), reference_filename)
        if ref_df is not None and not ref_df.empty and {"ISIN", "Security Name"}.issubset(ref_df.columns):
            name_lookup = ref_df.drop_duplicates("ISIN").set_index("ISIN")["Security Name"].to_dict()
            results["Security Name"] = results.index.map(lambda i: name_lookup.get(i, i))
        else:
            results["Security Name"] = results.index
    except Exception as e:
        current_app.logger.warning(f"Could not merge security names: {e}")
        results["Security Name"] = results.index

    results.sort_values("ContributionDifference", ascending=False, inplace=True)

    top_contrib = results.head(top_n).reset_index()
    top_detr = results.tail(top_n).iloc[::-1].reset_index()

    out_cols = ["ISIN", "Security Name", "ContributionDifference", "AverageContribution", "BaselineContribution"]

    return {
        "metric_name": metric_name,
        "fund_code": fund_code,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "baseline_date": baseline_date.strftime("%Y-%m-%d"),
        "data_source": data_source,
        "top_contributors": make_json_safe(top_contrib[out_cols].to_dict(orient="records")),
        "top_detractors": make_json_safe(top_detr[out_cols].to_dict(orient="records")),
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@inspect_bp.route("/<string:metric_name>/inspect", methods=["POST"])
def inspect_metric_contribution(metric_name):
    """API endpoint that returns JSON contribution analysis for the given metric."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request: No JSON body received."}), 400

    start_date = data.get("start_date")
    end_date = data.get("end_date")
    fund_code = data.get("fund_code")
    data_source = data.get("data_source", "Original")
    top_n = data.get("top_n", 10)

    if not all([start_date, end_date, fund_code]):
        return jsonify({"error": "Missing required parameters."}), 400

    try:
        results = _calculate_contributions(
            metric_name=metric_name,
            fund_code=fund_code,
            start_date_str=start_date,
            end_date_str=end_date,
            data_source=data_source,
            top_n=top_n,
        )
        return jsonify(results), 200
    except FileNotFoundError as e:
        current_app.logger.error(f"Inspect API – file not found: {e}")
        return jsonify({"error": str(e)}), 404
    except (ValueError, KeyError) as e:
        current_app.logger.error(f"Inspect API – bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Inspect API – server error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error."}), 500


@inspect_bp.route("/inspect/results")
def inspect_results_page():
    """Render the Inspect contribution results HTML page."""
    metric_name = request.args.get("metric_name")
    fund_code = request.args.get("fund_code")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    data_source = request.args.get("data_source", "Original")
    top_n = request.args.get("top_n", 10, type=int)

    if not all([metric_name, fund_code, start_date, end_date]):
        return (
            render_template(
                "error_page.html",
                error_message="Missing parameters for inspect results page.",
            ),
            400,
        )

    try:
        contrib_data = _calculate_contributions(
            metric_name, fund_code, start_date, end_date, data_source, top_n
        )
        error_message = None
    except Exception as e:
        current_app.logger.error(f"Inspect results – error: {e}", exc_info=True)
        contrib_data = {}
        error_message = str(e)

    context = {
        "metric_name": metric_name,
        "fund_code": fund_code,
        "start_date": start_date,
        "end_date": end_date,
        "data_source": data_source,
        "baseline_date": contrib_data.get("baseline_date", "N/A"),
        "top_contributors": contrib_data.get("top_contributors", []),
        "top_detractors": contrib_data.get("top_detractors", []),
        "error_message": error_message,
    }

    return render_template("inspect_results.html", **context) 