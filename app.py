# This file defines the main entry point and structure for the Simple Data Checker Flask web application.
# It utilizes the Application Factory pattern (`create_app`) to initialize and configure the Flask app.
# Key responsibilities include:
# - Creating the Flask application instance.
# - Setting up basic configuration (like the secret key).
# - Ensuring necessary folders (like the instance folder) exist.
# - Registering Blueprints (`main_bp`, `metric_bp`, `security_bp`, `fund_bp`) from the `views`
#   directory, which contain the application's routes and view logic.
# - Providing a conditional block (`if __name__ == '__main__':`) to run the development server
#   when the script is executed directly.
# This modular structure using factories and blueprints makes the application more organized and scalable.

# This file contains the main Flask application factory.
from flask import Flask
import os

# Import configurations and utilities (potentially needed by factory setup later)
# from config import DATA_FOLDER, COLOR_PALETTE # Not directly used in factory itself yet
# from utils import _is_date_like, parse_fund_list # Not directly used in factory itself yet

def create_app():
    """Factory function to create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=True) # instance_relative_config=True allows for instance folder config

    # Basic configuration (can be expanded later, e.g., loading from config file)
    app.config.from_mapping(
        SECRET_KEY='dev', # Default secret key for development. CHANGE for production!
        # Add other default configurations if needed
    )

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

    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(fund_bp)

    print("Registered Blueprints:")
    print(f"- {main_bp.name} (prefix: {main_bp.url_prefix})")
    print(f"- {metric_bp.name} (prefix: {metric_bp.url_prefix})")
    print(f"- {security_bp.name} (prefix: {security_bp.url_prefix})")
    print(f"- {fund_bp.name} (prefix: {fund_bp.url_prefix})")

    # Add a simple test route to confirm app creation (optional)
    @app.route('/hello')
    def hello():
        return 'Hello, World! App factory is working.'

    return app

# --- Application Execution --- 
if __name__ == '__main__':
    app = create_app() # Create the app instance using the factory
    app.run(debug=True) # Run in debug mode for development 