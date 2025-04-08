# This file defines the main entry point and structure for the Simple Data Checker Flask web application.
# It utilizes the Application Factory pattern (`create_app`) to initialize and configure the Flask app.
# Key responsibilities include:
# - Creating the Flask application instance.
# - Setting up basic configuration (like the secret key).
# - Ensuring necessary folders (like the instance folder) exist.
# - Registering Blueprints (`main_bp`, `metric_bp`, `security_bp`, `fund_bp`, `exclusion_bp`) from the `views`
#   directory, which contain the application's routes and view logic.
# - Providing a conditional block (`if __name__ == '__main__':`) to run the development server
#   when the script is executed directly.
# This modular structure using factories and blueprints makes the application more organized and scalable.

# This file contains the main Flask application factory.
from flask import Flask, render_template, Blueprint, jsonify
import os
import logging
# --- Add imports for the new route ---
import subprocess
import sys # To get python executable path
# --- End imports ---

# Import configurations and utilities (potentially needed by factory setup later)
from config import DATA_FOLDER, COLOR_PALETTE # Uncommented import
# from utils import _is_date_like, parse_fund_list # Not directly used in factory itself yet

def create_app():
    """Factory function to create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=True) # instance_relative_config=True allows for instance folder config

    # Basic configuration (can be expanded later, e.g., loading from config file)
    app.config.from_mapping(
        SECRET_KEY='dev', # Default secret key for development. CHANGE for production!
        # Add other default configurations if needed
    )

    # Load configuration from config.py
    app.config.from_object('config')

    # Ensure the instance folder exists (if using instance_relative_config)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # Already exists

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

    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(fund_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(exclusion_bp)
    app.register_blueprint(comparison_bp)
    app.register_blueprint(weight_bp)

    print("Registered Blueprints:")
    print(f"- {main_bp.name} (prefix: {main_bp.url_prefix})")
    print(f"- {metric_bp.name} (prefix: {metric_bp.url_prefix})")
    print(f"- {security_bp.name} (prefix: {security_bp.url_prefix})")
    print(f"- {fund_bp.name} (prefix: {fund_bp.url_prefix})")
    print(f"- {api_bp.name} (prefix: {api_bp.url_prefix})")
    print(f"- {exclusion_bp.name} (prefix: {exclusion_bp.url_prefix})")
    print(f"- {comparison_bp.name} (prefix: {comparison_bp.url_prefix})")
    print(f"- {weight_bp.name} (prefix: {weight_bp.url_prefix})")

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
    app.run(debug=True) # Run in debug mode for development 