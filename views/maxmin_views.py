# views/maxmin_views.py
# This module defines the Flask routes for the Max/Min Value Breach feature.
# It provides a dashboard and details pages for values exceeding configured thresholds in Spread files.

from flask import Blueprint, render_template, request, url_for, current_app
import os
import logging
import urllib.parse
from maxmin_processing import get_breach_summary, get_breach_details, DEFAULT_MAX_THRESHOLD, DEFAULT_MIN_THRESHOLD
from config import DATA_FOLDER, ID_COLUMN

maxmin_bp = Blueprint('maxmin_bp', __name__, template_folder='../templates')

@maxmin_bp.route('/maxmin/dashboard')
def dashboard():
    """Displays the Max/Min Value Breach dashboard with summary counts for each file and breach type."""
    current_app.logger.info("Accessing max/min breach dashboard.")
    try:
        # Get thresholds from query parameters (optional)
        max_str = request.args.get('max', str(DEFAULT_MAX_THRESHOLD))
        min_str = request.args.get('min', str(DEFAULT_MIN_THRESHOLD))
        try:
            max_threshold = float(max_str)
        except ValueError:
            max_threshold = DEFAULT_MAX_THRESHOLD
            current_app.logger.warning(f"Invalid max value '{max_str}', using default {max_threshold}.")
        try:
            min_threshold = float(min_str)
        except ValueError:
            min_threshold = DEFAULT_MIN_THRESHOLD
            current_app.logger.warning(f"Invalid min value '{min_str}', using default {min_threshold}.")

        summary_data = get_breach_summary(
            data_folder=current_app.config['DATA_FOLDER'],
            max_threshold=max_threshold,
            min_threshold=min_threshold
        )
        # Add details URLs for dashboard tiles
        for data in summary_data.values():
            data['max_details_url'] = url_for('.details', filename=data['filename'], breach_type='max', max=max_threshold, min=min_threshold)
            data['min_details_url'] = url_for('.details', filename=data['filename'], breach_type='min', max=max_threshold, min=min_threshold)
        return render_template('maxmin_dashboard.html', summary_data=list(summary_data.values()), max_threshold=max_threshold, min_threshold=min_threshold, DEFAULT_MAX_THRESHOLD=DEFAULT_MAX_THRESHOLD, DEFAULT_MIN_THRESHOLD=DEFAULT_MIN_THRESHOLD)
    except Exception as e:
        current_app.logger.error(f"Error generating max/min dashboard: {e}", exc_info=True)
        return render_template('error.html', message="Could not generate max/min dashboard."), 500

@maxmin_bp.route('/maxmin/details/<path:filename>/<breach_type>')
def details(filename, breach_type):
    """Displays the detailed list of max or min breaches for a specific file."""
    current_app.logger.info(f"Accessing max/min breach details for file: {filename}, type: {breach_type}")
    try:
        max_str = request.args.get('max', str(DEFAULT_MAX_THRESHOLD))
        min_str = request.args.get('min', str(DEFAULT_MIN_THRESHOLD))
        try:
            max_threshold = float(max_str)
        except ValueError:
            max_threshold = DEFAULT_MAX_THRESHOLD
        try:
            min_threshold = float(min_str)
        except ValueError:
            min_threshold = DEFAULT_MIN_THRESHOLD
        breaches, total_count = get_breach_details(
            filename,
            breach_type=breach_type,
            data_folder=current_app.config['DATA_FOLDER'],
            max_threshold=max_threshold,
            min_threshold=min_threshold
        )
        # Prepare static columns for table header (from first item if available)
        static_columns = []
        if breaches:
            static_columns = list(breaches[0].get('static_info', {}).keys())
        # Generate URLs for security details page
        for item in breaches:
            safe_sec_id = urllib.parse.quote_plus(str(item['id']))
            # Use the metric name (derived from filename, e.g., 'sec_Spread')
            metric_name = item['file'].replace('.csv', '')
            item['details_url'] = url_for(
                'security.security_details',
                metric_name=metric_name,
                security_id=safe_sec_id
            )
        return render_template(
            'maxmin_details.html',
            filename=filename,
            breach_type=breach_type,
            breaches=breaches,
            max_threshold=max_threshold,
            min_threshold=min_threshold,
            total_count=total_count,
            static_columns=static_columns,
            id_column=ID_COLUMN
        )
    except Exception as e:
        current_app.logger.error(f"Error generating max/min details for {filename}: {e}", exc_info=True)
        return render_template('error.html', message=f"Could not generate max/min details for {filename} ({breach_type})."), 500 