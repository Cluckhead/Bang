# Purpose: API endpoints for generating comprehensive synthetic analytics CSVs
# Provides frontend-callable endpoints to generate CSV exports with all SpreadOMatic analytics

import os
import threading
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, current_app, send_file, Response, render_template
import pandas as pd

from views.api_core import time_api_calls
from analytics.synth_analytics_csv_processor import (
    generate_comprehensive_analytics_csv,
    get_available_analytics_list,
    get_latest_date_from_csv,
    ENHANCED_ANALYTICS_AVAILABLE
)

# Blueprint for synthetic analytics API
synth_analytics_bp = Blueprint(
    "synth_analytics_bp",
    __name__,
    url_prefix="/api/synth_analytics"
)

# Job manager for background processing
analytics_job_manager = {}
analytics_job_lock = threading.Lock()


@synth_analytics_bp.route("/", methods=["GET"])
def analytics_dashboard():
    """Serve the comprehensive analytics dashboard page."""
    return render_template('synth_analytics_dashboard.html')


@synth_analytics_bp.route("/info", methods=["GET"])
@time_api_calls
def get_analytics_info() -> Response:
    """Get information about available analytics and latest date."""
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        
        # Get latest date info
        latest_date, price_df = get_latest_date_from_csv(data_folder)
        
        if latest_date is None:
            return jsonify({
                "error": "Could not determine latest date from sec_Price.csv"
            }), 400
        
        # Count securities with data for latest date
        securities_count = 0
        if price_df is not None:
            securities_with_data = price_df[price_df[latest_date].notna()]
            securities_count = len(securities_with_data)
        
        # Get available analytics list
        analytics_list = get_available_analytics_list()
        
        return jsonify({
            "latest_date": latest_date,
            "securities_count": securities_count,
            "total_securities": len(price_df) if price_df is not None else 0,
            "available_analytics": analytics_list,
            "analytics_count": len(analytics_list),
            "enhanced_analytics_available": ENHANCED_ANALYTICS_AVAILABLE
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting analytics info: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@synth_analytics_bp.route("/generate", methods=["POST"])
@time_api_calls
def generate_analytics_csv() -> Response:
    """Start background job to generate comprehensive analytics CSV."""
    try:
        data = request.get_json() or {}
        output_filename = data.get('output_filename')  # Optional custom filename
        
        # Create background job
        job_id = str(uuid.uuid4())
        
        with analytics_job_lock:
            analytics_job_manager[job_id] = {
                'status': 'queued',
                'progress': 0,
                'total': 100,
                'result': None,
                'error': None,
                'output_path': None
            }
        
        # Start background thread
        actual_app = current_app._get_current_object()
        thread = threading.Thread(
            target=run_analytics_job,
            args=(actual_app, job_id, output_filename),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'message': 'Analytics generation started in background'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error starting analytics generation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@synth_analytics_bp.route("/job_status/<job_id>", methods=["GET"])
@time_api_calls
def get_job_status(job_id: str) -> Response:
    """Get status of analytics generation job."""
    try:
        with analytics_job_lock:
            job = analytics_job_manager.get(job_id)
        
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        
        response = {
            'job_id': job_id,
            'status': job['status'],
            'progress': job['progress'],
            'total': job['total']
        }
        
        if job['status'] == 'completed':
            response['result'] = job['result']
            response['output_path'] = job['output_path']
        elif job['status'] == 'error':
            response['error'] = job['error']
        
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"Error getting job status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@synth_analytics_bp.route("/download/<job_id>", methods=["GET"])
@time_api_calls
def download_analytics_csv(job_id: str) -> Response:
    """Download the generated analytics CSV file."""
    try:
        with analytics_job_lock:
            job = analytics_job_manager.get(job_id)
        
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        
        if job['status'] != 'completed':
            return jsonify({"error": "Job not completed yet"}), 400
        
        output_path = job.get('output_path')
        if not output_path or not os.path.exists(output_path):
            return jsonify({"error": "Output file not found"}), 404
        
        # Send file for download
        filename = os.path.basename(output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading analytics CSV: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@synth_analytics_bp.route("/list_files", methods=["GET"])
@time_api_calls
def list_analytics_files() -> Response:
    """List previously generated analytics CSV files."""
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        
        # Find analytics CSV files
        files = []
        for filename in os.listdir(data_folder):
            if filename.startswith('comprehensive_analytics_') and filename.endswith('.csv'):
                filepath = os.path.join(data_folder, filename)
                stat = os.stat(filepath)
                files.append({
                    'filename': filename,
                    'size_bytes': stat.st_size,
                    'created_timestamp': stat.st_mtime,
                    'created_date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        # Sort by creation time (newest first)
        files.sort(key=lambda x: x['created_timestamp'], reverse=True)
        
        return jsonify({
            'files': files,
            'count': len(files)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error listing analytics files: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@synth_analytics_bp.route("/download_file/<filename>", methods=["GET"])
@time_api_calls
def download_analytics_file(filename: str) -> Response:
    """Download a specific analytics CSV file by filename."""
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        
        # Validate filename for security
        if not filename.startswith('comprehensive_analytics_') or not filename.endswith('.csv'):
            return jsonify({"error": "Invalid filename"}), 400
        
        filepath = os.path.join(data_folder, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading analytics file: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def run_analytics_job(app, job_id: str, output_filename: Optional[str] = None) -> None:
    """Background worker to generate analytics CSV."""
    with app.app_context():
        try:
            with analytics_job_lock:
                analytics_job_manager[job_id]['status'] = 'running'
                analytics_job_manager[job_id]['progress'] = 10
            
            data_folder = app.config["DATA_FOLDER"]
            
            # Update progress
            with analytics_job_lock:
                analytics_job_manager[job_id]['progress'] = 25
            
            # Generate the analytics CSV
            success, message, output_path = generate_comprehensive_analytics_csv(
                data_folder, output_filename
            )
            
            if success:
                with analytics_job_lock:
                    analytics_job_manager[job_id]['status'] = 'completed'
                    analytics_job_manager[job_id]['progress'] = 100
                    analytics_job_manager[job_id]['result'] = {
                        'message': message,
                        'filename': os.path.basename(output_path) if output_path else None
                    }
                    analytics_job_manager[job_id]['output_path'] = output_path
            else:
                with analytics_job_lock:
                    analytics_job_manager[job_id]['status'] = 'error'
                    analytics_job_manager[job_id]['error'] = message
                    
        except Exception as e:
            app.logger.error(f"Analytics job {job_id} failed: {e}", exc_info=True)
            with analytics_job_lock:
                analytics_job_manager[job_id]['status'] = 'error'
                analytics_job_manager[job_id]['error'] = str(e)
