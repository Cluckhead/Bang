# views/price_matching_views.py
# This module defines the Flask routes for the Price Matching feature.

from flask import Blueprint, render_template, request, url_for, current_app, jsonify
import os
import logging
from datetime import datetime, timedelta
from data_processing.price_matching_processing import (
    get_historical_results,
    run_price_matching_check,
    run_manual_check_for_date
)
from core import config

# Create blueprint
price_matching_bp = Blueprint("price_matching_bp", __name__, template_folder="../templates")

# --- Routes ---

@price_matching_bp.route("/price_matching/dashboard")
def dashboard():
    """Displays the price matching dashboard with historical data and current status."""
    current_app.logger.info("Accessing price matching dashboard.")
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        
        # Get historical results
        historical_data = get_historical_results(data_folder)
        
        # Get latest result from run_all_checks cache or run a fresh check
        kpi_json_path = os.path.join(data_folder, "dashboard_kpis.json")
        latest_result = None
        try:
            import json
            with open(kpi_json_path, "r", encoding="utf-8") as f:
                kpis = json.load(f)
                latest_result = kpis.get("price_matching", {})
        except Exception as e:
            current_app.logger.warning(f"Could not load latest price matching result from KPIs: {e}")
            # Fall back to running a fresh check (don't save to historical log)
            latest_result = run_price_matching_check(data_folder, save_historical=False)
        
        # Process historical data for charting
        chart_data = []
        for row in historical_data:
            try:
                chart_data.append({
                    'date': row['date'],
                    'match_percentage': float(row['match_percentage']),
                    'total_comparisons': int(row['total_comparisons']),
                    'matches': int(row['matches']),
                    'total_sec_price_securities': int(row['total_sec_price_securities']),
                    'timestamp': row['timestamp']
                })
            except (ValueError, KeyError) as e:
                current_app.logger.warning(f"Skipping invalid historical record: {e}")
                continue
        
        # Sort by date (ensure proper string sorting)
        chart_data.sort(key=lambda x: str(x['date']))
        
        # Identify missing days (where checks weren't run)
        missing_days = []
        if len(chart_data) > 1:
            # Find gaps between consecutive dates
            for i in range(1, len(chart_data)):
                prev_date_str = str(chart_data[i-1]['date'])
                curr_date_str = str(chart_data[i]['date'])
                
                try:
                    prev_date = datetime.strptime(prev_date_str, '%Y%m%d')
                    curr_date = datetime.strptime(curr_date_str, '%Y%m%d')
                    
                    # Check for gaps > 1 day (excluding weekends would be more complex)
                    days_diff = (curr_date - prev_date).days
                    if days_diff > 1:
                        # There's a gap - could be weekends or missing checks
                        for j in range(1, days_diff):
                            missing_date = prev_date + timedelta(days=j)
                            # Only consider weekdays as potentially missing
                            if missing_date.weekday() < 5:  # Monday=0, Friday=4
                                missing_days.append(missing_date.strftime('%Y%m%d'))
                except ValueError as e:
                    current_app.logger.warning(f"Could not parse dates for missing day detection: {prev_date_str}, {curr_date_str}: {e}")
                    continue
        
        current_app.logger.info(f"Price matching dashboard: {len(chart_data)} historical records, {len(missing_days)} missing days")
        current_app.logger.debug(f"Historical data sample: {chart_data[:3] if chart_data else 'No data'}")
        
        return render_template(
            "price_matching_dashboard.html",
            latest_result=latest_result,
            historical_data=chart_data,
            missing_days=missing_days
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating price matching dashboard: {e}", exc_info=True)
        return render_template(
            "error.html", 
            message="Could not generate price matching dashboard."
        ), 500


@price_matching_bp.route("/price_matching/run_manual_check", methods=["POST"])
def run_manual_check():
    """API endpoint to run manual price matching check for a specific date."""
    try:
        data = request.get_json()
        target_date = data.get('date')
        
        if not target_date:
            return jsonify({"error": "Date parameter is required"}), 400
        
        # Validate date format (YYYYMMDD)
        try:
            datetime.strptime(target_date, '%Y%m%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYYMMDD"}), 400
        
        current_app.logger.info(f"Running manual price matching check for date: {target_date}")
        
        data_folder = current_app.config["DATA_FOLDER"]
        result = run_manual_check_for_date(target_date, data_folder)
        
        if result is None:
            return jsonify({"error": f"No BondAnalyticsResults file found for date {target_date}"}), 404
        
        return jsonify({
            "success": True,
            "result": result,
            "message": f"Manual check completed for {target_date}"
        })
        
    except Exception as e:
        current_app.logger.error(f"Error running manual price matching check: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@price_matching_bp.route("/price_matching/api/historical_data")
def api_historical_data():
    """API endpoint to get historical price matching data as JSON."""
    try:
        data_folder = current_app.config["DATA_FOLDER"]
        historical_data = get_historical_results(data_folder)
        
        # Process for JSON response
        processed_data = []
        for row in historical_data:
            try:
                processed_data.append({
                    'date': row['date'],
                    'match_percentage': float(row['match_percentage']),
                    'total_comparisons': int(row['total_comparisons']),
                    'matches': int(row['matches']),
                    'total_sec_price_securities': int(row['total_sec_price_securities']),
                    'timestamp': row['timestamp']
                })
            except (ValueError, KeyError):
                continue
        
        return jsonify(processed_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting historical price matching data: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500 