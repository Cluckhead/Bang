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
from flask import Flask, render_template, Blueprint, jsonify
import os
import logging
from logging.handlers import RotatingFileHandler # Import handler
# --- Add imports for the new route ---
import subprocess
import sys # To get python executable path
# --- End imports ---

# Import configurations and utilities
from config import COLOR_PALETTE # Import other needed configs
from utils import get_data_folder_path # Import the path utility

def create_app():
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
        file_handler.setLevel(logging.INFO) # Log INFO and higher to file
        app.logger.addHandler(file_handler)
        app.logger.info(f"File logging configured to: {log_file_path}")
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
    from views.comparison_views import comparison_bp
    from views.weight_views import weight_bp
    # --- Import new blueprints ---
    from views.duration_comparison_views import duration_comparison_bp
    from views.spread_duration_comparison_views import spread_duration_comparison_bp
    # --- End import new blueprints ---
    from views.curve_views import curve_bp # Import the new blueprint

    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(fund_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(exclusion_bp)
    app.register_blueprint(comparison_bp)
    app.register_blueprint(weight_bp)
    # --- Register new blueprints ---
    app.register_blueprint(duration_comparison_bp)
    app.register_blueprint(spread_duration_comparison_bp)
    # --- End register new blueprints ---
    app.register_blueprint(curve_bp) # Register the new blueprint

    app.logger.info("Registered Blueprints:")
    app.logger.info(f"- {main_bp.name} (prefix: {main_bp.url_prefix})")
    app.logger.info(f"- {metric_bp.name} (prefix: {metric_bp.url_prefix})")
    app.logger.info(f"- {security_bp.name} (prefix: {security_bp.url_prefix})")
    app.logger.info(f"- {fund_bp.name} (prefix: {fund_bp.url_prefix})")
    app.logger.info(f"- {api_bp.name} (prefix: {api_bp.url_prefix})")
    app.logger.info(f"- {exclusion_bp.name} (prefix: {exclusion_bp.url_prefix})")
    app.logger.info(f"- {comparison_bp.name} (prefix: {comparison_bp.url_prefix})")
    app.logger.info(f"- {weight_bp.name} (prefix: {weight_bp.url_prefix})")
    # --- Print new blueprints ---
    print(f"- {duration_comparison_bp.name} (prefix: {duration_comparison_bp.url_prefix})")
    print(f"- {spread_duration_comparison_bp.name} (prefix: {spread_duration_comparison_bp.url_prefix})")
    # --- End print new blueprints ---
    app.logger.info(f"- {curve_bp.name} (prefix: {curve_bp.url_prefix})") # Log registration

    # Add a simple test route to confirm app creation (optional)
    @app.route('/hello')
    def hello():
        return 'Hello, World! App factory is working.'

    # --- Add the new cleanup route ---
    @app.route('/run-cleanup', methods=['POST'])
    def run_cleanup():
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

    return app

# --- Application Execution ---
if __name__ == '__main__':
    app = create_app() # Create the app instance using the factory
    app.run(debug=True, host='0.0.0.0') # Run in debug mode for development, accessible on network 