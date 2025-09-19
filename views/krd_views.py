"""views/krd_views.py
Purpose: Provide routes for comparing aggregated Key-Rate Duration (KRD) sums against security-level Duration values.
Two versions are exposed:
 • Original (portfolio) – compares *KRD.csv* vs *sec_duration.csv*
 • S&P switched – compares *KRDSP.csv* vs *sec_durationSP.csv*
The view highlights breaches where the absolute gap exceeds the configured tolerance (default 0.25).
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Tuple
import pandas as pd
from flask import Blueprint, current_app, render_template, request, jsonify
import logging

krd_bp = Blueprint("krd_bp", __name__, template_folder="../templates")

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def load_krd_vs_duration(data_folder: str, *, sp: bool = False, tol: float = 1.0) -> Tuple[pd.DataFrame, List[str]]:
    """Return a DataFrame with ISIN, Date, krd_sum, duration, abs_diff, breach flag."""

    krd_file = "KRDSP.csv" if sp else "KRD.csv"
    krd_path = os.path.join(data_folder, krd_file)
    if not os.path.exists(krd_path):
        raise FileNotFoundError(f"{krd_file} not found in {data_folder}")

    # Load KRD (wide buckets) with scientific notation support
    krd_df = pd.read_csv(krd_path)
    logger.info(f"Loaded KRD file: {krd_file} with shape {krd_df.shape}")

    # Identify bucket columns (all except metadata)
    bucket_cols = [c for c in krd_df.columns if c not in {"ISIN", "Date"}]
    if not bucket_cols:
        raise ValueError("No tenor bucket columns detected in KRD file.")
    logger.info(f"KRD bucket columns: {bucket_cols}")

    # Convert bucket columns to float (handles scientific notation)
    for col in bucket_cols:
        before_na = krd_df[col].isna().sum()
        krd_df[col] = pd.to_numeric(krd_df[col], errors='coerce')
        after_na = krd_df[col].isna().sum()
        if after_na > before_na:
            logger.warning(f"Column {col}: {after_na - before_na} values could not be converted to float and were set to NaN.")

    # Calculate KRD sum for each security and date
    krd_df["bucket_sum"] = krd_df[bucket_cols].sum(axis=1, skipna=True)
    logger.info(f"Aggregated KRD bucket_sum for {len(krd_df)} rows. Example: {krd_df[['ISIN', 'Date', 'bucket_sum']].head(3).to_dict(orient='records')}")

    # Keep only necessary columns
    krd_summary = krd_df[["ISIN", "Date", "bucket_sum"]].copy()

    # ------------------------------------------------------------------
    # Load Security Duration data
    # ------------------------------------------------------------------
    sec_dur_file = "sec_durationSP.csv" if sp else "sec_duration.csv"
    sec_dur_path = os.path.join(data_folder, sec_dur_file)
    if not os.path.exists(sec_dur_path):
        # Fallback to regular sec_duration.csv if SP version doesn't exist
        sec_dur_path = os.path.join(data_folder, "sec_duration.csv")
        if not os.path.exists(sec_dur_path):
            raise FileNotFoundError(f"Security duration file not found in {data_folder}")

    sec_dur_df = pd.read_csv(sec_dur_path)
    logger.info(f"Loaded Security Duration file: {sec_dur_file} with shape {sec_dur_df.shape}")
    
    # Identify date columns in sec_duration.csv (exclude metadata columns)
    metadata_cols = {"ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"}
    date_cols = [c for c in sec_dur_df.columns if c not in metadata_cols]
    
    # Convert date columns to float (handles scientific notation)
    for col in date_cols:
        before_na = sec_dur_df[col].isna().sum()
        sec_dur_df[col] = pd.to_numeric(sec_dur_df[col], errors='coerce')
        after_na = sec_dur_df[col].isna().sum()
        if after_na > before_na:
            logger.warning(f"Duration column {col}: {after_na - before_na} values could not be converted to float and were set to NaN.")
    
    # Melt the sec_duration data to long format
    sec_dur_melted = sec_dur_df.melt(
        id_vars=["ISIN", "Security Name"] if "Security Name" in sec_dur_df.columns else ["ISIN"],
        value_vars=date_cols,
        var_name="Date",
        value_name="duration"
    )
    logger.info(f"Melted security duration to long format. Example: {sec_dur_melted[['ISIN', 'Date', 'duration']].head(3).to_dict(orient='records')}")
    
    # Clean up the date format to match KRD format
    sec_dur_melted["Date"] = pd.to_datetime(sec_dur_melted["Date"]).dt.strftime("%Y-%m-%d")
    
    # ------------------------------------------------------------------
    # Merge KRD with Security Duration
    # ------------------------------------------------------------------
    merged = pd.merge(krd_summary, sec_dur_melted, how="inner", on=["ISIN", "Date"])
    logger.info(f"Merged KRD and Duration. Example: {merged[['ISIN', 'Date', 'bucket_sum', 'duration']].head(3).to_dict(orient='records')}")
    
    # Remove rows where duration is NaN
    merged = merged.dropna(subset=["duration"])
    
    # Calculate absolute difference
    merged["abs_diff"] = (merged["bucket_sum"] - merged["duration"]).abs()
    merged["breach"] = merged["abs_diff"] > tol
    logger.info(f"Calculated abs_diff and breach. Example: {merged[['ISIN', 'Date', 'bucket_sum', 'duration', 'abs_diff', 'breach']].head(3).to_dict(orient='records')}")

    # Get all unique dates for date selector
    all_dates = sorted(merged["Date"].unique())
    
    # Log unique dates in KRD and Duration files
    krd_dates = krd_df['Date'].unique()
    krd_dates_clean = [d for d in krd_dates if isinstance(d, str)]
    logger.info(
        f"KRD file unique dates: {krd_dates_clean[:10]}... (total {len(krd_dates_clean)}) "
        f"min={min(krd_dates_clean) if krd_dates_clean else 'N/A'} "
        f"max={max(krd_dates_clean) if krd_dates_clean else 'N/A'}"
    )

    sec_dur_dates = sec_dur_df.columns if 'Date' in sec_dur_df.columns else []
    logger.info(f"Duration file date columns: {date_cols[:10]}... (total {len(date_cols)})")

    # After melting, log unique dates in melted duration
    melted_dates = sec_dur_melted['Date'].unique()
    melted_dates_clean = [d for d in melted_dates if isinstance(d, str)]
    logger.info(
        f"Melted duration unique dates: {melted_dates_clean[:10]}... (total {len(melted_dates_clean)}) "
        f"min={min(melted_dates_clean) if melted_dates_clean else 'N/A'} "
        f"max={max(melted_dates_clean) if melted_dates_clean else 'N/A'}"
    )

    # After merging, log unique dates and shape
    merged_dates = merged['Date'].unique()
    merged_dates_clean = [d for d in merged_dates if isinstance(d, str)]
    logger.info(
        f"Merged DataFrame unique dates: {merged_dates_clean[:10]}... (total {len(merged_dates_clean)}) "
        f"min={min(merged_dates_clean) if merged_dates_clean else 'N/A'} "
        f"max={max(merged_dates_clean) if merged_dates_clean else 'N/A'}"
    )
    logger.info(f"Merged DataFrame shape: {merged.shape}")
    logger.info(f"Merged DataFrame head: {merged.head(5).to_dict(orient='records')}")

    return merged, all_dates


def load_krd_vs_duration_historical(data_folder: str, isin: str, *, sp: bool = False) -> pd.DataFrame:
    """Return historical KRD vs Duration data for a specific ISIN, with both regular and S&P data."""
    
    try:
        # Load both regular and S&P data for comparison
        df_regular, _ = load_krd_vs_duration(data_folder, sp=False, tol=0.0)
        df_sp, _ = load_krd_vs_duration(data_folder, sp=True, tol=0.0)
        
        # Filter for specific ISIN
        df_regular_isin = df_regular[df_regular["ISIN"] == isin].copy()
        df_sp_isin = df_sp[df_sp["ISIN"] == isin].copy()
        
        # Sort by date
        df_regular_isin = df_regular_isin.sort_values("Date")
        df_sp_isin = df_sp_isin.sort_values("Date")
        
        # Add data source labels
        df_regular_isin["data_source"] = "Portfolio"
        df_sp_isin["data_source"] = "S&P"
        
        # Combine both datasets
        df_combined = pd.concat([df_regular_isin, df_sp_isin], ignore_index=True)
        
        return df_combined
        
    except Exception as e:
        logger.error(f"Error loading historical data for ISIN {isin}: {e}")
        return pd.DataFrame()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@krd_bp.route("/krd/comparison")
def krd_comparison():
    """Main KRD comparison page showing breaches."""
    sp = request.args.get("sp", "0") == "1"
    tol = float(request.args.get("tol", 1))
    data_folder = current_app.config["DATA_FOLDER"]

    try:
        df_all, date_list = load_krd_vs_duration(data_folder, sp=sp, tol=tol)
        sel_date = request.args.get("date") or (date_list[-1] if date_list else None)
        if sel_date:
            df = df_all[df_all["Date"] == sel_date]
        else:
            df = df_all

        # Keep only breaches (abs diff > tol)
        df = df[df["abs_diff"] > tol]
        
        # Sort by absolute difference descending to show worst breaches first
        df = df.sort_values("abs_diff", ascending=False)
        
    except Exception as exc:
        logger.error("Error building KRD comparison: %s", exc, exc_info=True)
        return render_template("error.html", message=str(exc))

    # Convert to dict for Jinja
    rows: List[Dict[str, Any]] = df.to_dict(orient="records")
    context = {
        "rows": rows,
        "sp": sp,
        "tolerance": tol,
        "dates": date_list,
        "selected_date": sel_date,
    }
    return render_template("krd_vs_duration.html", **context)


@krd_bp.route("/krd/historical/<isin>")
def krd_historical_chart(isin: str):
    """Display historical KRD vs Duration chart for a specific ISIN."""
    sp = request.args.get("sp", "0") == "1"
    data_folder = current_app.config["DATA_FOLDER"]

    try:
        df_historical = load_krd_vs_duration_historical(data_folder, isin, sp=sp)
        
        if df_historical.empty:
            return render_template("error.html", 
                                 message=f"No historical data found for ISIN: {isin}")
        
        # Get security name if available
        security_name = df_historical["Security Name"].iloc[0] if "Security Name" in df_historical.columns else "Unknown"
        
        # Separate data by source
        portfolio_data = df_historical[df_historical["data_source"] == "Portfolio"][["Date", "bucket_sum", "duration"]].to_dict(orient="records")
        sp_data = df_historical[df_historical["data_source"] == "S&P"][["Date", "bucket_sum", "duration"]].to_dict(orient="records")
        
        context = {
            "isin": isin,
            "security_name": security_name,
            "portfolio_data": portfolio_data,
            "sp_data": sp_data,
            "sp": sp
        }
        
        return render_template("krd_historical_chart.html", **context)
        
    except Exception as exc:
        logger.error("Error building historical KRD chart: %s", exc, exc_info=True)
        return render_template("error.html", message=str(exc))


@krd_bp.route("/api/krd/historical/<isin>")
def api_krd_historical_data(isin: str):
    """API endpoint to get historical KRD vs Duration data for a specific ISIN."""
    sp = request.args.get("sp", "0") == "1"
    data_folder = current_app.config["DATA_FOLDER"]

    try:
        df_historical = load_krd_vs_duration_historical(data_folder, isin, sp=sp)
        
        if df_historical.empty:
            return jsonify({"error": f"No data found for ISIN: {isin}"}), 404
        
        # Return data as JSON
        return jsonify({
            "isin": isin,
            "data": df_historical[["Date", "bucket_sum", "duration", "abs_diff"]].to_dict(orient="records")
        })
        
    except Exception as exc:
        logger.error("Error fetching historical KRD data: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500 