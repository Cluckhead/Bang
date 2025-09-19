"""
Search functionality for securities.
Provides API endpoints for autocomplete search of securities from reference.csv.
"""

import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
import logging

# Define the Blueprint
search_bp = Blueprint("search", __name__)

logger = logging.getLogger(__name__)


def load_securities_for_search(data_folder_path: str):
    """
    Load securities data from reference.csv for search functionality.
    Returns a DataFrame with relevant columns for search.
    """
    reference_file_path = os.path.join(data_folder_path, "reference.csv")
    
    try:
        if os.path.exists(reference_file_path):
            # Load only the columns we need for search
            columns_to_load = ["ISIN", "Security Name", "Position Currency", "Ticker", "Security Sub Type"]
            df = pd.read_csv(
                reference_file_path,
                usecols=columns_to_load,
                dtype=str,
                encoding_errors="replace",
                on_bad_lines="skip",
            )
            
            # Clean up the data
            df = df.dropna(subset=["ISIN", "Security Name"])
            df = df.drop_duplicates(subset=["ISIN"])
            
            # Fill NaN values with empty strings for consistent searching
            df = df.fillna("")
            
            return df
        else:
            logger.warning(f"Reference file not found at {reference_file_path}")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error loading securities for search: {e}", exc_info=True)
        return pd.DataFrame()


def search_securities(query: str, data_folder_path: str, limit: int = 10):
    """
    Search securities based on query string.
    Searches across ISIN, Security Name, Currency, and Ticker.
    """
    df = load_securities_for_search(data_folder_path)
    
    if df.empty:
        return []
    
    # Convert query to lowercase for case-insensitive search
    query_lower = query.lower()
    
    # Create search conditions
    conditions = (
        df["ISIN"].str.lower().str.contains(query_lower, na=False) |
        df["Security Name"].str.lower().str.contains(query_lower, na=False) |
        df["Position Currency"].str.lower().str.contains(query_lower, na=False) |
        df["Ticker"].str.lower().str.contains(query_lower, na=False)
    )
    
    # Filter results
    results_df = df[conditions].head(limit)
    
    # Convert to list of dictionaries for JSON response
    results = []
    for _, row in results_df.iterrows():
        results.append({
            "isin": row["ISIN"],
            "security_name": row["Security Name"],
            "currency": row["Position Currency"],
            "ticker": row["Ticker"],
            "security_sub_type": row["Security Sub Type"]
        })
    
    return results


@search_bp.route("/api/search-securities", methods=["POST"])
def search_securities_endpoint():
    """
    API endpoint for searching securities.
    Expects JSON: {"query": "search_term"}
    Returns JSON: {"results": [{"isin": "...", "security_name": "...", ...}]}
    """
    try:
        data = request.get_json()
        if not data or "query" not in data:
            return jsonify({"error": "Query parameter is required"}), 400
        
        query = data["query"].strip()
        if len(query) < 2:
            return jsonify({"results": []})
        
        data_folder = current_app.config.get("DATA_FOLDER")
        if not data_folder:
            return jsonify({"error": "Server configuration error"}), 500
        
        results = search_securities(query, data_folder, limit=15)
        
        return jsonify({
            "results": results,
            "count": len(results)
        })
    
    except Exception as e:
        logger.error(f"Error in search endpoint: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@search_bp.route("/api/search-securities-suggestions", methods=["GET"])
def search_securities_suggestions():
    """
    API endpoint for getting search suggestions (top securities).
    Returns a sample of securities for quick access.
    """
    try:
        data_folder = current_app.config.get("DATA_FOLDER")
        if not data_folder:
            return jsonify({"error": "Server configuration error"}), 500
        
        df = load_securities_for_search(data_folder)
        if df.empty:
            return jsonify({"suggestions": []})
        
        # Get a sample of securities, preferring ones with complete data
        suggestions_df = df.head(10)
        
        suggestions = []
        for _, row in suggestions_df.iterrows():
            suggestions.append({
                "isin": row["ISIN"],
                "security_name": row["Security Name"],
                "currency": row["Position Currency"],
                "ticker": row["Ticker"],
                "security_sub_type": row["Security Sub Type"]
            })
        
        return jsonify({
            "suggestions": suggestions,
            "count": len(suggestions)
        })
    
    except Exception as e:
        logger.error(f"Error in suggestions endpoint: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500