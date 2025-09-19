import os
import json
import yaml
import csv
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, current_app
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings_bp', __name__)

SETTINGS_FILE = 'settings.yaml'
CHANGE_LOG_FILENAME = 'settings_change_log.csv'

def load_combined_settings():
    """Load settings from the combined YAML file."""
    try:
        settings_path = Path(SETTINGS_FILE)
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                data = yaml.safe_load(f)
                # Ensure new keys exist with sensible defaults
                if data is None:
                    data = {}
                if 'template_help_urls' not in data:
                    data['template_help_urls'] = {}
                return data
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
    
    # Return default structure if file doesn't exist
    return {
        'app_config': {},
        'spread_files': {'spread_files': []},
        'metric_file_map': {'metrics': {}},
        'data_extender_settings': {},
        'file_delivery': {'monitors': {}},
        'maxmin_thresholds': {},
        'attribution_columns': {'prefixes': {}, 'l1_factors': [], 'l2_groups': {}},
        'date_patterns': {'date_patterns': []},
        'field_aliases': {},
        'comparison_config': {},
        'template_help_urls': {}
    }

def save_combined_settings(settings):
    """Save settings to the combined YAML file and log the change."""
    try:
        # Save to YAML file
        with open(SETTINGS_FILE, 'w') as f:
            yaml.dump(settings, f, default_flow_style=False, sort_keys=False)
        
        # Log the change
        log_settings_change("Settings updated via settings page")
        
        return True
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return False

def log_settings_change(description):
    """Log a settings change to the change log CSV file."""
    try:
        # Ensure configured data directory exists
        data_dir = Path(current_app.config.get('DATA_FOLDER', 'Data'))
        data_dir.mkdir(parents=True, exist_ok=True)

        # Check if file exists
        log_path = data_dir / CHANGE_LOG_FILENAME
        file_exists = log_path.exists()
        
        # Write to CSV
        with open(log_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['timestamp', 'description'])
            
            # Write header if new file
            if not file_exists:
                writer.writeheader()
            
            # Write the log entry
            writer.writerow({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'description': description
            })
    except Exception as e:
        logger.error(f"Error logging settings change: {e}")

def load_change_log():
    """Load the settings change log."""
    changes = []
    try:
        data_dir = Path(current_app.config.get('DATA_FOLDER', 'Data'))
        log_path = data_dir / CHANGE_LOG_FILENAME
        if log_path.exists():
            with open(log_path, 'r') as f:
                reader = csv.DictReader(f)
                changes = list(reader)
    except Exception as e:
        logger.error(f"Error loading change log: {e}")
    
    return changes

@settings_bp.route('/settings')
def settings_page():
    """Display the settings page."""
    settings = load_combined_settings()
    change_log = load_change_log()

    # Build list of available templates (without extension)
    try:
        templates_dir = Path(current_app.root_path) / 'templates'
        template_names = []
        if templates_dir.exists():
            for p in templates_dir.glob('*.html'):
                # Skip base or partial templates if needed
                if p.name.startswith('_'):
                    continue
                name_without_ext = p.stem
                template_names.append(name_without_ext)
        template_names.sort()
    except Exception as e:
        logger.error(f"Error enumerating templates: {e}")
        template_names = []

    return render_template(
        'settings_page.html',
        settings=settings,
        change_log=change_log,
        template_names=template_names,
    )

@settings_bp.route('/api/save-settings', methods=['POST'])
def save_settings_api():
    """API endpoint to save settings."""
    try:
        settings = request.json
        
        # Clean up array handling for spread files
        if isinstance(settings, dict) and 'spread_files' in settings:
            inner = settings['spread_files'].get('spread_files') if isinstance(settings['spread_files'], dict) else None
            if isinstance(inner, dict):
                # Convert indexed dict to list
                spread_list = []
                for key in sorted(inner.keys(), key=lambda k: str(k)):
                    item = inner.get(key)
                    if isinstance(item, dict):
                        spread_list.append(item)
                settings['spread_files']['spread_files'] = spread_list
            elif isinstance(inner, list):
                # Already a list, leave as-is
                pass
            else:
                # Ensure correct shape
                if isinstance(settings['spread_files'], dict):
                    settings['spread_files']['spread_files'] = []
        
        # Clean up file delivery monitors
        if isinstance(settings, dict) and 'file_delivery' in settings and isinstance(settings['file_delivery'], dict) and 'monitors' in settings['file_delivery']:
            monitors = settings['file_delivery']['monitors']
            if isinstance(monitors, dict):
                for monitor_key in list(monitors.keys()):
                    monitor = monitors.get(monitor_key) or {}
                    if 'date_parse' not in monitor or not isinstance(monitor.get('date_parse'), dict):
                        monitor['date_parse'] = {
                            'source': 'filename',
                            'regex': '',
                            'format': ''
                        }
                    else:
                        # Ensure date_parse has all required fields
                        if 'source' not in monitor['date_parse']:
                            monitor['date_parse']['source'] = 'filename'
                    # Ensure group field exists
                    if 'group' not in monitor:
                        monitor['group'] = 'FileDelivery'
                    monitors[monitor_key] = monitor
        
        # Ensure maxmin thresholds have all required fields
        if isinstance(settings, dict) and 'maxmin_thresholds' in settings and isinstance(settings['maxmin_thresholds'], dict):
            for file_key, threshold in list(settings['maxmin_thresholds'].items()):
                if not isinstance(threshold, dict):
                    threshold = {}
                if 'display_name' not in threshold:
                    threshold['display_name'] = str(file_key).replace('.csv', '').replace('_', ' ').title()
                if 'group' not in threshold:
                    threshold['group'] = 'Default'
                settings['maxmin_thresholds'][file_key] = threshold
        
        # Save the settings
        if save_combined_settings(settings):
            return jsonify({'status': 'success', 'message': 'Settings saved successfully'})
        else:
            return jsonify({'status': 'error', 'error': 'Failed to save settings'}), 500
            
    except Exception as e:
        logger.error(f"Error in save_settings_api: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@settings_bp.route('/api/reload-settings', methods=['GET'])
def reload_settings_api():
    """API endpoint to reload settings from file."""
    try:
        settings = load_combined_settings()
        return jsonify({'status': 'success', 'settings': settings})
    except Exception as e:
        logger.error(f"Error reloading settings: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500