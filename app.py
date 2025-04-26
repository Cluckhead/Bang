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
from logging.handlers import RotatingFileHandler # Import handler
# --- Add imports for the new route ---
import subprocess
import sys # To get python executable path
import json
import threading
import time
import datetime
# --- End imports ---

# Import configurations and utilities
from config import COLOR_PALETTE # Import other needed configs
from utils import get_data_folder_path # Import the path utility

# Add typing imports for type hints
from typing import List, Dict, Any

def create_app() -> Flask:
    """Factory function to create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=True) # instance_relative_config=True allows for instance folder config
    app.logger.info(f"Application root path: {app.root_path}")

    # Basic configuration (can be expanded later, e.g., loading from config file)
    app.config.from_mapping(
        SECRET_KEY='dev', # Default secret key for development. CHANGE for production!
        # Add other default configurations if needed
    )

    # Load configuration from config.py (e.g., COLOR_PALETTE)
    app.config.from_object('config')
    app.logger.info("Loaded configuration from config.py")

    # --- Determine and set the Data Folder Path --- 
    # Use the utility function to get the absolute data path, using the app's root path as the base
    # This ensures consistency whether the path in config.py is relative or absolute
    absolute_data_path = get_data_folder_path(app_root_path=app.root_path)
    app.config['DATA_FOLDER'] = absolute_data_path
    app.logger.info(f"Data folder path set to: {app.config['DATA_FOLDER']}")
    # --- End Data Folder Path Setup ---

    # Ensure the instance folder exists (needed for logging)
    try:
        os.makedirs(app.instance_path, exist_ok=True) # exist_ok=True prevents error if exists
        app.logger.info(f"Instance folder ensured at: {app.instance_path}")
    except OSError as e:
        app.logger.error(f"Could not create instance folder at {app.instance_path}: {e}", exc_info=True)
        # Depending on severity, might want to raise an exception or exit

    # --- Centralized Logging Configuration --- 
    # Remove Flask's default handlers
    app.logger.handlers.clear()
    app.logger.setLevel(logging.DEBUG) # Set the app logger level (DEBUG captures everything)

    # Formatter
    log_formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )

    # File Handler (Rotating)
    log_file_path = os.path.join(app.instance_path, 'app.log')
    max_log_size = 1024 * 1024 * 10 # 10 MB
    backup_count = 5
    try:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_log_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(logging.DEBUG) # Log DEBUG and higher to file
        app.logger.addHandler(file_handler)
        app.logger.info(f"File logging configured to: {log_file_path} (Level: DEBUG)")
    except Exception as e:
        app.logger.error(f"Failed to configure file logging to {log_file_path}: {e}", exc_info=True)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    # Set console level potentially higher for less noise (e.g., INFO) or keep DEBUG for development
    console_handler.setLevel(logging.DEBUG)
    app.logger.addHandler(console_handler)

    app.logger.info("Centralized logging configured (File & Console).")
    # --- End Logging Configuration ---

    # Configure logging (consider moving to a dedicated logging setup function)
    # Note: BasicConfig should ideally be called only once. If utils.py also calls it,
    # it might conflict or be ineffective here. A more robust setup is recommended.
    # logging.basicConfig(level=logging.INFO,
    #                     format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
    # app.logger.info("Logging configured.") # BasicConfig might be configured in utils already

    # Serve static files (for JS, CSS, etc.)
    # Note: static_url_path defaults to /static, static_folder defaults to 'static' in root
    # No need to set app.static_folder = 'static' explicitly unless changing the folder name/path

    # --- Register Blueprints ---
    from views.main_views import main_bp
    from views.metric_views import metric_bp
    from views.security_views import security_bp
    from views.fund_views import fund_bp
    from views.api_views import api_bp
    from views.exclusion_views import exclusion_bp
    # from views.comparison_views import comparison_bp # OLD - Replaced by generic
    from views.weight_views import weight_bp
    # --- Import new blueprints ---
    # from views.duration_comparison_views import duration_comparison_bp # OLD - Replaced by generic
    # from views.spread_duration_comparison_views import spread_duration_comparison_bp # OLD - Replaced by generic
    # --- End import new blueprints ---
    from views.curve_views import curve_bp # Import the new blueprint
    from views.issue_views import issue_bp # Import the issue tracking blueprint
    from views.attribution_views import attribution_bp # Import the attribution blueprint
    from views.generic_comparison_views import generic_comparison_bp # NEW Generic Comparison BP
    from views.staleness_views import staleness_bp # Import the staleness blueprint
    from views.maxmin_views import maxmin_bp # Import the max/min value breach blueprint

    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(fund_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(exclusion_bp)
    # app.register_blueprint(comparison_bp) # OLD - Replaced by generic
    app.register_blueprint(weight_bp)
    # --- Register new blueprints ---
    # app.register_blueprint(duration_comparison_bp) # OLD - Replaced by generic
    # app.register_blueprint(spread_duration_comparison_bp) # OLD - Replaced by generic
    # --- End register new blueprints ---
    app.register_blueprint(curve_bp) # Register the new blueprint
    app.register_blueprint(issue_bp) # Register the issue tracking blueprint
    app.register_blueprint(attribution_bp) # Register the attribution blueprint
    app.register_blueprint(generic_comparison_bp, url_prefix='/compare') # NEW - Register generic comparison with a base prefix
    app.register_blueprint(staleness_bp) # Register the staleness blueprint
    app.register_blueprint(maxmin_bp) # Register the max/min value breach blueprint

    app.logger.info("Registered Blueprints:")
    app.logger.info(f"- {main_bp.name} (prefix: {main_bp.url_prefix})")
    app.logger.info(f"- {metric_bp.name} (prefix: {metric_bp.url_prefix})")
    app.logger.info(f"- {security_bp.name} (prefix: {security_bp.url_prefix})")
    app.logger.info(f"- {fund_bp.name} (prefix: {fund_bp.url_prefix})")
    app.logger.info(f"- {api_bp.name} (prefix: {api_bp.url_prefix})")
    app.logger.info(f"- {exclusion_bp.name} (prefix: {exclusion_bp.url_prefix})")
    # app.logger.info(f"- {comparison_bp.name} (prefix: {comparison_bp.url_prefix})") # OLD
    app.logger.info(f"- {weight_bp.name} (prefix: {weight_bp.url_prefix})")
    # --- Print new blueprints ---
    # print(f"- {duration_comparison_bp.name} (prefix: {duration_comparison_bp.url_prefix})") # OLD
    # print(f"- {spread_duration_comparison_bp.name} (prefix: {spread_duration_comparison_bp.url_prefix})") # OLD
    # --- End print new blueprints ---
    app.logger.info(f"- {curve_bp.name} (prefix: {curve_bp.url_prefix})") # Log registration
    app.logger.info(f"- {issue_bp.name} (prefix: {issue_bp.url_prefix})") # Log registration for issues
    app.logger.info(f"- {attribution_bp.name} (prefix: {attribution_bp.url_prefix})") # Log registration for attribution
    app.logger.info(f"- {generic_comparison_bp.name} (prefix: {generic_comparison_bp.url_prefix})") # Log NEW generic comparison
    app.logger.info(f"- {staleness_bp.name} (prefix: {staleness_bp.url_prefix})") # Log registration for staleness
    app.logger.info(f"- {maxmin_bp.name} (prefix: {maxmin_bp.url_prefix})") # Log registration for max/min value breach

    # Add a simple test route to confirm app creation (optional)
    @app.route('/hello')
    def hello() -> str:
        return 'Hello, World! App factory is working.'

    # --- Add the new cleanup route ---
    @app.route('/run-cleanup', methods=['POST'])
    def run_cleanup() -> Response:
        """Endpoint to trigger the process_data.py script."""
        script_path = os.path.join(os.path.dirname(__file__), 'process_data.py')
        python_executable = sys.executable # Use the same python that runs flask

        if not os.path.exists(script_path):
            app.logger.error(f"Cleanup script not found at: {script_path}")
            return jsonify({'status': 'error', 'message': 'Cleanup script not found.'}), 500

        app.logger.info(f"Attempting to run cleanup script: {script_path}")
        try:
            # Run the script using the same Python interpreter that is running Flask
            # Capture stdout and stderr, decode as UTF-8, handle potential errors
            result = subprocess.run(
                [python_executable, script_path],
                capture_output=True,
                text=True,
                check=False, # Don't raise exception on non-zero exit code
                encoding='utf-8' # Explicitly set encoding
            )

            log_output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

            if result.returncode == 0:
                app.logger.info(f"Cleanup script finished successfully. Output:\n{log_output}")
                return jsonify({'status': 'success', 'output': result.stdout or "No output", 'error': result.stderr}), 200
            else:
                app.logger.error(f"Cleanup script failed with return code {result.returncode}. Output:\n{log_output}")
                return jsonify({'status': 'error', 'message': 'Cleanup script failed.', 'output': result.stdout, 'error': result.stderr}), 500

        except Exception as e:
            app.logger.error(f"Exception occurred while running cleanup script: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'An exception occurred: {e}'}), 500
    # --- End new route ---

    # --- Scheduled API Calls: manual scheduler loop using threading ---
    schedules_file = os.path.join(app.instance_path, 'schedules.json')
    if not os.path.exists(schedules_file):
        with open(schedules_file, 'w') as f:
            json.dump([], f)

    # Helper functions to load/save schedules
    def load_schedules() -> List[Dict[str, Any]]:
        with open(schedules_file, 'r') as f:
            return json.load(f)
    def save_schedules(schedules: List[Dict[str, Any]]) -> None:
        with open(schedules_file, 'w') as f:
            json.dump(schedules, f)

    # Job runner function
    def run_scheduled_job(schedule: Dict[str, Any]) -> None:
        with app.app_context():
            payload = {
                'date_mode': schedule['date_mode'],
                'write_mode': schedule['write_mode'],
                'funds': schedule['funds']
            }
            # Calculate dates at runtime based on relative offsets
            import pandas as pd
            from pandas.tseries.offsets import BDay
            import datetime
            today = pd.Timestamp(datetime.datetime.now().date())
            most_recent_bd = today if today.weekday() < 5 else today - BDay(1) # fallback: today if weekday, else previous business day
            if schedule['date_mode'] == 'quick':
                days_back = schedule['days_back']
                end_date = (most_recent_bd - BDay(0)).date()
                start_date = end_date - pd.Timedelta(days=days_back)
                payload['days_back'] = days_back
                payload['end_date'] = end_date.strftime('%Y-%m-%d')
            else:
                start_offset = schedule['start_offset']
                end_offset = schedule['end_offset']
                end_date = (most_recent_bd - BDay(end_offset)).date()
                start_date = end_date - pd.Timedelta(days=(start_offset - end_offset))
                payload['start_date'] = start_date.strftime('%Y-%m-%d')
                payload['custom_end_date'] = end_date.strftime('%Y-%m-%d')
            response = app.test_client().post('/run_api_calls', json=payload)
            app.logger.info(f"Scheduled job {schedule['id']} executed. Status: {response.status_code}")

    # Manual scheduling loop
    def schedule_loop() -> None:
        last_checked = None
        while True:
            now = datetime.datetime.now()
            current_minute = now.replace(second=0, microsecond=0)
            if current_minute != last_checked:
                last_checked = current_minute
                for sched in load_schedules():
                    sched_time = datetime.datetime.strptime(sched['schedule_time'], '%H:%M').time()
                    if sched_time.hour == now.hour and sched_time.minute == now.minute:
                        try:
                            run_scheduled_job(sched)
                        except Exception as e:
                            app.logger.error(f"Error running scheduled job {sched['id']}: {e}", exc_info=True)
            time.sleep(1)

    threading.Thread(target=schedule_loop, daemon=True).start()
    app.logger.info("Started manual schedule loop thread")
    # --- End manual scheduling ---

    return app

# --- Application Execution ---
if __name__ == '__main__':
    app = create_app() # Create the app instance using the factory
    app.run(debug=True, host='0.0.0.0') # Run in debug mode for development, accessible on network 