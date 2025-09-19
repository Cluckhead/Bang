# Purpose: Script to run all major data quality checks (staleness, max/min, file delivery, Z-score metrics, price matching) and write results to Data/dashboard_kpis.json for dashboard caching. Uses file locking for safe concurrent writes. Also generates automatic tickets for data exceptions.

import os
import sys
import json
import logging
from filelock import FileLock, Timeout
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
import pandas as pd
import time

from core import config
from core.io_lock import install_pandas_file_locks
from analytics.staleness_processing import get_staleness_summary
from analytics.maxmin_processing import get_breach_summary
from analytics.file_delivery_processing import load_monitors, update_log, build_dashboard_summary
from analytics.metric_calculator import calculate_latest_metrics
from core.data_loader import load_and_process_data
from data_processing.price_matching_processing import run_price_matching_check
from analytics import ticket_processing

# Install file-locked CSV I/O for this standalone script as well
try:
    install_pandas_file_locks()
except Exception:
    pass

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Reduce third-party lock noise in terminal; follow project pattern
logging.getLogger("filelock").setLevel(logging.WARNING)
logging.getLogger("io_lock").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def run_staleness_check() -> Dict[str, Any]:
    try:
        exclusions_path = os.path.join(config.DATA_FOLDER, config.EXCLUSIONS_FILE)
        exclusions_df = None
        if os.path.exists(exclusions_path):
            from core.utils import load_exclusions
            exclusions_df = load_exclusions(exclusions_path)
        summary = get_staleness_summary(
            data_folder=config.DATA_FOLDER,
            exclusions_df=exclusions_df,
            threshold_days=getattr(config, 'STALENESS_THRESHOLD_DAYS', 5),
        )
        
        # Generate tickets for staleness issues
        generate_staleness_tickets(summary, config.DATA_FOLDER)
        
        return summary
    except Exception as e:
        logger.error(f"Error in staleness check: {e}", exc_info=True)
        return {"error": str(e)}

def run_maxmin_check() -> Dict[str, Any]:
    try:
        summary = get_breach_summary(
            data_folder=config.DATA_FOLDER,
            threshold_config=config.MAXMIN_THRESHOLDS,
        )
        
        # Generate tickets for max/min breaches
        generate_maxmin_tickets(summary, config.DATA_FOLDER)
        
        return summary
    except Exception as e:
        logger.error(f"Error in max/min check: {e}", exc_info=True)
        return {"error": str(e)}

def run_file_delivery_check() -> Dict[str, Any]:
    try:
        monitors = load_monitors()
        update_log(monitors)
        summary = build_dashboard_summary(monitors)
        return summary
    except Exception as e:
        logger.error(f"Error in file delivery check: {e}", exc_info=True)
        return {"error": str(e)}

def run_zscore_metrics() -> Dict[str, Any]:
    results = {}
    try:
        metric_map = config.METRIC_FILE_MAP
        for metric_key, metric_cfg in metric_map.items():
            ts_file = metric_cfg.get('ts_file')
            sp_ts_file = metric_cfg.get('sp_ts_file')
            if not ts_file:
                continue
            primary_path = os.path.join(config.DATA_FOLDER, ts_file)
            secondary_path = os.path.join(config.DATA_FOLDER, sp_ts_file) if sp_ts_file else None
            if not os.path.exists(primary_path):
                logger.warning(f"Primary file missing for metric {metric_key}: {primary_path}")
                continue
            load_result = load_and_process_data(
                primary_filename=ts_file,
                secondary_filename=sp_ts_file,
                data_folder_path=config.DATA_FOLDER,
                filter_sp_valid=False,
            )
            (
                primary_df,
                pri_fund_cols,
                pri_bench_col,
                secondary_df,
                sec_fund_cols,
                sec_bench_col,
            ) = load_result
            metrics_df = calculate_latest_metrics(
                primary_df=primary_df,
                primary_fund_cols=pri_fund_cols,
                primary_benchmark_col=pri_bench_col,
                secondary_df=secondary_df,
                secondary_fund_cols=sec_fund_cols,
                secondary_benchmark_col=sec_bench_col,
                secondary_prefix="S&P ",
            )
            # Convert to dict for JSON
            if metrics_df is not None and not metrics_df.empty:
                results[metric_key] = metrics_df.reset_index().to_dict(orient="records")
                
                # Generate tickets for extreme Z-scores
                generate_zscore_tickets(metrics_df, metric_key, config.DATA_FOLDER)
            else:
                results[metric_key] = []
        return results
    except Exception as e:
        logger.error(f"Error in Z-score metrics: {e}", exc_info=True)
        return {"error": str(e)}

def run_price_matching_check_wrapper() -> Dict[str, Any]:
    try:
        summary = run_price_matching_check(
            data_folder=config.DATA_FOLDER,
            bond_analytics_folder="Minny/Resources",
            save_historical=True
        )
        
        # Generate tickets for low match rates (less than 90%)
        generate_price_matching_tickets(summary, config.DATA_FOLDER)
        
        return summary
    except Exception as e:
        logger.error(f"Error in price matching check: {e}", exc_info=True)
        return {"error": str(e)}

def generate_staleness_tickets(summary: Dict[str, Any], data_folder_path: str) -> None:
    """Generate tickets for staleness issues detected in the summary."""
    try:
        for file_name, stale_data in summary.items():
            if isinstance(stale_data, dict) and stale_data.get("stale_count", 0) > 0:
                stale_securities = stale_data.get("stale_securities", [])
                for security in stale_securities:
                    entity_id = security.get("ISIN", "Unknown")
                    days_stale = security.get("days_stale", 0)
                    details = f"{file_name}: Stale for {days_stale} days"
                    ticket_processing.create_ticket(
                        source_check="Staleness",
                        entity_id=entity_id,
                        details=details,
                        data_folder_path=data_folder_path
                    )
    except Exception as e:
        logger.error(f"Error generating staleness tickets: {e}", exc_info=True)


def generate_maxmin_tickets(summary: Dict[str, Any], data_folder_path: str) -> None:
    """Generate tickets for max/min threshold breaches."""
    try:
        for file_name, breach_data in summary.items():
            if isinstance(breach_data, dict):
                # Max breaches
                max_breaches = breach_data.get("max_breaches", [])
                for breach in max_breaches:
                    entity_id = breach.get("ISIN", "Unknown")
                    value = breach.get("value", "N/A")
                    threshold = breach.get("threshold", "N/A")
                    details = f"{file_name}: Value {value} > threshold {threshold}"
                    ticket_processing.create_ticket(
                        source_check="MaxMin",
                        entity_id=entity_id,
                        details=details,
                        data_folder_path=data_folder_path
                    )
                
                # Min breaches
                min_breaches = breach_data.get("min_breaches", [])
                for breach in min_breaches:
                    entity_id = breach.get("ISIN", "Unknown")
                    value = breach.get("value", "N/A")
                    threshold = breach.get("threshold", "N/A")
                    details = f"{file_name}: Value {value} < threshold {threshold}"
                    ticket_processing.create_ticket(
                        source_check="MaxMin",
                        entity_id=entity_id,
                        details=details,
                        data_folder_path=data_folder_path
                    )
    except Exception as e:
        logger.error(f"Error generating max/min tickets: {e}", exc_info=True)


def generate_zscore_tickets(metrics_df: pd.DataFrame, metric_key: str, data_folder_path: str) -> None:
    """Generate tickets for extreme Z-scores (|Z| > 3)."""
    try:
        for _, row in metrics_df.iterrows():
            fund_code = row.get("Fund Code", "Unknown")
            for col_name, value in row.items():
                if "Z-Score" in col_name and value is not None and abs(value) > 3:
                    source_field = col_name.replace(" Z-Score", "")
                    details = f"{metric_key} {source_field}: Z-Score = {value:.2f}"
                    ticket_processing.create_ticket(
                        source_check="ZScore",
                        entity_id=fund_code,
                        details=details,
                        data_folder_path=data_folder_path
                    )
    except Exception as e:
        logger.error(f"Error generating Z-score tickets: {e}", exc_info=True)


def generate_price_matching_tickets(summary: Dict[str, Any], data_folder_path: str) -> None:
    """Generate tickets for low price match rates (<90%)."""
    try:
        if "error" in summary:
            # Generate ticket for price matching system error
            ticket_processing.create_ticket(
                source_check="PriceMatching",
                entity_id="SYSTEM",
                details=f"Price matching check failed: {summary['error']}",
                data_folder_path=data_folder_path
            )
        else:
            match_percentage = summary.get("match_percentage", 0)
            if match_percentage < 90:
                total_comparisons = summary.get("total_comparisons", 0)
                matches = summary.get("matches", 0)
                latest_date = summary.get("latest_date", "Unknown")
                
                details = f"Price match rate below 90%: {match_percentage:.1f}% ({matches}/{total_comparisons}) on {latest_date}"
                ticket_processing.create_ticket(
                    source_check="PriceMatching",
                    entity_id="SYSTEM",
                    details=details,
                    data_folder_path=data_folder_path
                )
    except Exception as e:
        logger.error(f"Error generating price matching tickets: {e}", exc_info=True)


def main() -> None:
    # Enable batch mode for ticket writes for performance
    ticket_processing.enable_batch_mode()
    logger.info("Running all data quality checks...")

    overall_start = time.perf_counter()
    step_timings: List[tuple[str, float]] = []

    def timed(label: str, func):
        start = time.perf_counter()
        result = func()
        duration = time.perf_counter() - start
        step_timings.append((label, duration))
        logger.info("%s completed in %.2f seconds", label, duration)
        return result

    # Initialize ticket files if they don't exist
    ticket_processing.initialize_ticket_files(config.DATA_FOLDER)

    results = {
        "timestamp": datetime.now().isoformat(),
        "staleness": timed("Staleness Check", run_staleness_check),
        "maxmin": timed("Max/Min Check", run_maxmin_check),
        "file_delivery": timed("File Delivery Check", run_file_delivery_check),
        "zscore_metrics": timed("Z-Score Metrics", run_zscore_metrics),
        "price_matching": timed("Price Matching Check", run_price_matching_check_wrapper),
    }

    # Flush any pending ticket CSV writes collected during batch mode
    flush_start = time.perf_counter()
    ticket_processing.flush_batch_writes()
    step_timings.append(("Flush Ticket Writes", time.perf_counter() - flush_start))

    output_path = os.path.join(config.DATA_FOLDER, "dashboard_kpis.json")
    lock_path = output_path + ".lock"
    lock = FileLock(lock_path, timeout=30)
    try:
        with lock:
            write_start = time.perf_counter()
            # Convert NaN values to null for valid JSON
            def convert_nan_to_null(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {k: convert_nan_to_null(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_nan_to_null(item) for item in obj]
                elif isinstance(obj, float) and (obj != obj):  # NaN check
                    return None
                else:
                    return obj
            
            clean_results = convert_nan_to_null(results)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(clean_results, f, indent=2, default=str)
            step_timings.append(("Write dashboard_kpis.json", time.perf_counter() - write_start))
        logger.info("Results written to %s", output_path)
    except Timeout:
        logger.error(f"Timeout acquiring lock for {output_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error writing results: {e}", exc_info=True)
        sys.exit(1)

    total_duration = time.perf_counter() - overall_start
    logger.info("All data quality checks completed in %.2f seconds", total_duration)
    # Log breakdown
    for label, dur in step_timings:
        logger.info("Timing | %-28s : %.2f s", label, dur)

if __name__ == "__main__":
    main() 