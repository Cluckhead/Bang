# This file contains the main Flask application and routes.
from flask import Flask, render_template, jsonify
import os
import pandas as pd
import numpy as np
from data_processing import load_and_process_data, calculate_latest_metrics

app = Flask(__name__)
# Serve static files (for JS)
app.static_folder = 'static'

DATA_FOLDER = 'Data'

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    'blue', 'red', 'green', 'purple', '#FF7F50', # Coral
    '#6495ED', # CornflowerBlue
    '#DC143C', # Crimson
    '#00FFFF'  # Aqua
]

@app.route('/')
def index():
    """Renders the main dashboard page."""
    files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
    metrics = [os.path.splitext(f)[0] for f in files]
    return render_template('index.html', metrics=metrics)

@app.route('/metric/<metric_name>')
def metric_page(metric_name):
    """Renders the page for a specific metric, handling multiple fund columns."""
    filename = f"{metric_name}.csv"
    try:
        # Load data, get df, list of fund columns, and benchmark column
        df, fund_cols, benchmark_col = load_and_process_data(filename)
        latest_date_overall = df.index.get_level_values(0).max()
        # Calculate metrics for all fund columns vs benchmark
        latest_metrics = calculate_latest_metrics(df, fund_cols, benchmark_col)
        
        # Determine missing funds based on the presence of ANY NaN Z-score for that fund
        # Check across all potential Z-score columns
        z_score_cols = [col for col in latest_metrics.columns if 'Z-Score' in col]
        missing_latest = latest_metrics[latest_metrics[z_score_cols].isna().any(axis=1)]

        # --- Prepare data for JavaScript --- 
        charts_data_for_js = {}
        for fund_code in latest_metrics.index:
            if fund_code not in latest_metrics.index: continue

            fund_hist_data = df.xs(fund_code, level=1).sort_index()
            fund_latest_metrics = latest_metrics.loc[fund_code]
            # Fund is missing latest if *any* of its Z-scores are NaN
            is_missing_latest = fund_code in missing_latest.index

            labels = fund_hist_data.index.strftime('%Y-%m-%d').tolist()
            datasets = []

            # Add dataset for each fund column
            for i, fund_col in enumerate(fund_cols):
                fund_values = fund_hist_data[fund_col].round(3).fillna(np.nan).tolist()
                color = COLOR_PALETTE[i % len(COLOR_PALETTE)] # Cycle through colors
                datasets.append({
                    'label': fund_col,
                    'data': fund_values,
                    'borderColor': color,
                    'backgroundColor': color + '40', # Add some transparency for points
                    'tension': 0.1
                })
            
            # Add dataset for the benchmark column
            bench_values = fund_hist_data[benchmark_col].round(3).fillna(np.nan).tolist()
            datasets.append({
                'label': benchmark_col,
                'data': bench_values,
                'borderColor': 'black', # Make benchmark distinct
                'backgroundColor': 'grey',
                'borderDash': [5, 5], # Dashed line for benchmark
                'tension': 0.1
            })
            
            # Convert metrics row to dictionary, handling NaNs for JSON
            fund_latest_metrics_dict = fund_latest_metrics.round(3).where(pd.notnull(fund_latest_metrics), None).to_dict()
            
            charts_data_for_js[fund_code] = {
                'labels': labels,
                'datasets': datasets, # Now contains multiple fund datasets + benchmark
                'metrics': fund_latest_metrics_dict, # Contains metrics for all spreads
                'is_missing_latest': is_missing_latest,
                # Pass column names needed by JS chart title/table (benchmark already known)
                'fund_column_names': fund_cols 
            }

        return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json=jsonify(charts_data_for_js).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y'),
                               missing_funds=missing_latest,
                               # Pass list of fund cols and single benchmark col
                               fund_col_names = fund_cols, 
                               benchmark_col_name = benchmark_col)

    except FileNotFoundError:
        return f"Error: Data file '{filename}' not found.", 404
    except ValueError as ve:
        print(f"Value Error processing {metric_name}: {ve}")
        return f"Error processing {metric_name}: {ve}", 400
    except Exception as e:
        fund_code_context = fund_code if 'fund_code' in locals() else 'N/A'
        print(f"Error processing {metric_name} for fund {fund_code_context}: {e}")
        import traceback
        traceback.print_exc()
        return f"An error occurred processing {metric_name}: {e}", 500

if __name__ == '__main__':
    app.run(debug=True) 