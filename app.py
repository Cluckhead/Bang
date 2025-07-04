# This file defines the main entry point and structure for the Simple Data Checker Flask web application.
# It utilizes the Application Factory pattern (`create_app`) to initialize and configure the Flask app.
# Key responsibilities include:
# - Creating the Flask application instance.
# - Setting up basic configuration (like the secret key).
# - Ensuring necessary folders (like the instance folder) exist.
# - Determining and configuring the absolute data folder path using `utils.get_data_folder_path`.
# - Centralizing logging configuration (File and Console handlers).
# - Registering Blueprints (`main_bp`, `metric_bp`, `security_bp`, `fund_bp`, `exclusion_bp`, `comparison_bp`, `duration_comparison_bp`, `spread_duration_comparison_bp`, `api_bp`, `weight_bp`) from the `views`
#   directory, which contain the application\'s routes and view logic.
# - Providing a conditional block (`if __name__ == '__main__':`) to run the development server
#   when the script is executed directly.
# This modular structure using factories and blueprints makes the application more organized and scalable.

# This file contains the main Flask application factory.
from flask import Flask, render_template, Blueprint, jsonify, Response
import os
import logging
from logging.handlers import RotatingFileHandler  # Import handler

# --- Add imports for the new route ---
import subprocess
import sys  # To get python executable path
import json
import threading
import time
import re
from datetime import datetime, timedelta

# --- End imports ---

# Import configurations and utilities
from config import COLOR_PALETTE  # Import other needed configs
from utils import get_data_folder_path  # Import the path utility
from navigation_config import NAV_MENU

# Add typing imports for type hints
from typing import List, Dict, Any


def prune_old_logs(log_file_path, hours=24):
    """
    Prunes log entries older than the specified hours.
    
    Args:
        log_file_path: Path to the log file
        hours: Number of hours to keep logs for (default: 24)
    """
    if not os.path.exists(log_file_path):
        return  # No log file to prune yet
    
    try:
        # Get the cutoff time
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Read the current log file
        with open(log_file_path, 'r') as file:
            log_lines = file.readlines()
        
        # Initialize variables
        pruned_lines = []
        log_date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
        
        for line in log_lines:
            match = log_date_pattern.search(line)
            if match:
                try:
                    # Parse the timestamp in the log entry
                    log_time_str = match.group(1)
                    log_time = datetime.strptime(log_time_str, '%Y-%m-%d %H:%M:%S')
                    
                    # Keep only entries newer than the cutoff time
                    if log_time >= cutoff_time:
                        pruned_lines.append(line)
                except ValueError:
                    # If timestamp parsing fails, keep the line
                    pruned_lines.append(line)
            else:
                # If no timestamp is found, keep the line
                pruned_lines.append(line)
        
        # Write back the pruned log file
        with open(log_file_path, 'w') as file:
            file.writelines(pruned_lines)
        
        pruned_count = len(log_lines) - len(pruned_lines)
        print(f"Pruned {pruned_count} log entries older than {hours} hours")
        
    except Exception as e:
        print(f"Error pruning logs: {e}")


def create_app() -> Flask:
    print("create_app() called")
    """Factory function to create and configure the Flask app."""
    app = Flask(
        __name__, instance_relative_config=True
    )  # instance_relative_config=True allows for instance folder config
    app.logger.info(f"Application root path: {app.root_path}")

    # --- Centralized Logging Configuration for ALL loggers ---
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    # Set up root logger so all logs from all modules go to file and console
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    log_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )

    log_file_path = os.path.join(app.instance_path, "app.log")
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)

    # --- End root logger setup ---

    # Basic configuration (can be expanded later, e.g., loading from config file)
    app.config.from_mapping(
        SECRET_KEY="dev",  # Default secret key for development. CHANGE for production!
        # Add other default configurations if needed
    )

    # Load configuration from config.py (e.g., COLOR_PALETTE)
    app.config.from_object("config")
    app.logger.info("Loaded configuration from config.py")

    # --- Determine and set the Data Folder Path ---
    # Use the utility function to get the absolute data path, using the app's root path as the base
    # This ensures consistency whether the path in config.py is relative or absolute
    absolute_data_path = get_data_folder_path(app_root_path=app.root_path)
    app.config["DATA_FOLDER"] = absolute_data_path
    app.logger.info(f"Data folder path set to: {app.config['DATA_FOLDER']}")
    # --- End Data Folder Path Setup ---

    # Ensure the instance folder exists (needed for logging)
    try:
        os.makedirs(
            app.instance_path, exist_ok=True
        )  # exist_ok=True prevents error if exists
        app.logger.info(f"Instance folder ensured at: {app.instance_path}")
    except OSError as e:
        app.logger.error(
            f"Could not create instance folder at {app.instance_path}: {e}",
            exc_info=True,
        )
        # Depending on severity, might want to raise an exception or exit

    # --- Prune old logs before setting up new logging ---
    prune_old_logs(log_file_path, hours=24)
    
    # --- Register Blueprints ---
    try:
        from views.main_views import main_bp
        from views.metric_views import metric_bp
        from views.security_views import security_bp
        from views.fund_views import fund_bp
        from views.api_views import api_bp
        from views.exclusion_views import exclusion_bp
        from views.weight_views import weight_bp
        from views.curve_views import curve_bp
        from views.issue_views import issue_bp
        from views.attribution_views import attribution_bp
        from views.generic_comparison_views import generic_comparison_bp
        from views.staleness_views import staleness_bp
        from views.maxmin_views import maxmin_bp
        from views.watchlist_views import watchlist_bp
        from views.inspect_views import inspect_bp
    except ImportError as imp_err:
        app.logger.error(f"Blueprint import failed: {imp_err}", exc_info=True)
        raise
    except Exception as e:
        app.logger.error(
            f"Unexpected error during blueprint import: {e}", exc_info=True
        )
        raise

    try:
        app.register_blueprint(main_bp)
        app.register_blueprint(metric_bp)
        app.register_blueprint(security_bp)
        app.register_blueprint(fund_bp)
        app.register_blueprint(api_bp)
        app.register_blueprint(exclusion_bp)
        app.register_blueprint(weight_bp)
        app.register_blueprint(curve_bp)
        app.register_blueprint(issue_bp)
        app.register_blueprint(attribution_bp)
        app.register_blueprint(generic_comparison_bp, url_prefix="/compare")
        app.register_blueprint(staleness_bp)
        app.register_blueprint(maxmin_bp)
        app.register_blueprint(watchlist_bp)
        app.register_blueprint(inspect_bp)
        print("Registered watchlist_bp in create_app")
    except Exception as reg_err:
        app.logger.error(f"Blueprint registration failed: {reg_err}", exc_info=True)
        raise

    app.logger.info("Registered Blueprints:")
    app.logger.info(f"- {main_bp.name} (prefix: {main_bp.url_prefix})")
    app.logger.info(f"- {metric_bp.name} (prefix: {metric_bp.url_prefix})")
    app.logger.info(f"- {inspect_bp.name} (prefix: {inspect_bp.url_prefix})")
    app.logger.info(f"- {security_bp.name} (prefix: {security_bp.url_prefix})")
    app.logger.info(f"- {fund_bp.name} (prefix: {fund_bp.url_prefix})")
    app.logger.info(f"- {api_bp.name} (prefix: {api_bp.url_prefix})")
    app.logger.info(f"- {exclusion_bp.name} (prefix: {exclusion_bp.url_prefix})")
    app.logger.info(f"- {weight_bp.name} (prefix: {weight_bp.url_prefix})")
    app.logger.info(
        f"- {curve_bp.name} (prefix: {curve_bp.url_prefix})"
    )  # Log registration
    app.logger.info(
        f"- {issue_bp.name} (prefix: {issue_bp.url_prefix})"
    )  # Log registration for issues
    app.logger.info(
        f"- {attribution_bp.name} (prefix: {attribution_bp.url_prefix})"
    )  # Log registration for attribution
    app.logger.info(
        f"- {generic_comparison_bp.name} (prefix: {generic_comparison_bp.url_prefix})"
    )  # Log NEW generic comparison
    app.logger.info(
        f"- {staleness_bp.name} (prefix: {staleness_bp.url_prefix})"
    )  # Log registration for staleness
    app.logger.info(
        f"- {maxmin_bp.name} (prefix: {maxmin_bp.url_prefix})"
    )  # Log registration for max/min value breach
    app.logger.info(
        f"- {watchlist_bp.name} (prefix: {watchlist_bp.url_prefix})"
    )  # Log registration for Watchlist

    # Add a simple test route to confirm app creation (optional)
    @app.route("/hello")
    def hello() -> str:
        return "Hello, World! App factory is working."

    # --- Add the new cleanup route ---
    @app.route("/run-cleanup", methods=["POST"])
    def run_cleanup() -> Response:
        """Endpoint to trigger the *preprocessing* batch job.

        Instead of spawning a separate Python subprocess, we now call
        run_preprocessing.main directly, which improves error handling
        and avoids the overhead of launching an external interpreter.
        """

        try:
            from run_preprocessing import (
                main as run_preprocessing_main,
            )  # Local import to avoid circular deps

            start_time = time.perf_counter()

            # Execute the preprocessing pipeline synchronously.  For long-running
            # jobs consider dispatching to a background thread/queue – but for
            # now synchronous execution keeps things simple and deterministic.
            run_preprocessing_main()

            duration_s = time.perf_counter() - start_time

            msg = f"Preprocessing completed successfully in {duration_s:0.2f}s."
            app.logger.info(msg)
            # Include both 'output' (expected by frontend) and 'message' for consistency.
            return jsonify({"status": "success", "output": msg, "message": msg}), 200

        except FileNotFoundError as fnf_err:
            err_msg = f"Preprocessing failed – file not found: {fnf_err}"
            app.logger.error(err_msg, exc_info=True)
            return jsonify({"status": "error", "message": err_msg}), 500

        except Exception as exc:
            err_msg = f"Unexpected error during preprocessing: {exc}"
            app.logger.error(err_msg, exc_info=True)
            return jsonify({"status": "error", "message": err_msg}), 500

    # --- Scheduled API Calls: manual scheduler loop using threading ---
    schedules_file = os.path.join(app.instance_path, "schedules.json")
    if not os.path.exists(schedules_file):
        with open(schedules_file, "w") as f:
            json.dump([], f)

    # Helper functions to load/save schedules
    def load_schedules() -> List[Dict[str, Any]]:
        with open(schedules_file, "r") as f:
            return json.load(f)

    def save_schedules(schedules: List[Dict[str, Any]]) -> None:
        with open(schedules_file, "w") as f:
            json.dump(schedules, f)

    # Job runner function
    def run_scheduled_job(schedule: Dict[str, Any]) -> None:
        with app.app_context():
            payload = {
                "date_mode": schedule["date_mode"],
                "write_mode": schedule["write_mode"],
                "funds": schedule["funds"],
            }
            # Calculate dates at runtime based on relative offsets
            import pandas as pd
            from pandas.tseries.offsets import BDay
            
            today = pd.Timestamp(datetime.now().date())
            most_recent_bd = (
                today if today.weekday() < 5 else today - BDay(1)
            )  # fallback: today if weekday, else previous business day
            if schedule["date_mode"] == "quick":
                days_back = schedule["days_back"]
                end_date = (most_recent_bd - BDay(0)).date()
                start_date = end_date - pd.Timedelta(days=days_back)
                payload["days_back"] = days_back
                payload["end_date"] = end_date.strftime("%Y-%m-%d")
            else:
                start_offset = schedule["start_offset"]
                end_offset = schedule["end_offset"]
                end_date = (most_recent_bd - BDay(end_offset)).date()
                start_date = end_date - pd.Timedelta(days=(start_offset - end_offset))
                payload["start_date"] = start_date.strftime("%Y-%m-%d")
                payload["custom_end_date"] = end_date.strftime("%Y-%m-%d")
            response = app.test_client().post("/run_api_calls", json=payload)
            app.logger.info(
                f"Scheduled job {schedule['id']} executed. Status: {response.status_code}"
            )

    # Manual scheduling loop
    def schedule_loop() -> None:
        last_checked = None
        while True:
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)
            if current_minute != last_checked:
                last_checked = current_minute
                for sched in load_schedules():
                    sched_time = datetime.strptime(
                        sched["schedule_time"], "%H:%M"
                    ).time()
                    if sched_time.hour == now.hour and sched_time.minute == now.minute:
                        try:
                            run_scheduled_job(sched)
                        except Exception as e:
                            app.logger.error(
                                f"Error running scheduled job {sched['id']}: {e}",
                                exc_info=True,
                            )
            time.sleep(1)

    threading.Thread(target=schedule_loop, daemon=True).start()
    app.logger.info("Started manual schedule loop thread")
    # --- End manual scheduling ---

    # Add this context processor after app creation (inside create_app or after app = Flask(...))
    @app.context_processor
    def inject_nav_menu():
        return {'NAV_MENU': NAV_MENU}

    return app


# --- Application Execution ---
if __name__ == "__main__":
    app = create_app()  # Create the app instance using the factory
    app.run(
        debug=True, host="0.0.0.0"
    )  # Run in debug mode for development, accessible on network