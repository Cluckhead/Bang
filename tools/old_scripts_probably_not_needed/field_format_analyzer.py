# field_format_analyzer.py
# Purpose: Scan all CSV files under the project "Data" directory, infer data format (Text, Integer, Float, Date) for each column, store results in a JSON file, and if an existing JSON is present, create a FieldReport.csv detailing any changes.

import os
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
from pandas.api.types import infer_dtype
import re
import yaml

# --------------------------- Configuration --------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Assumes script in tools/

# --------------------------- Resolve Data Directory --------------------------- #
# Read data folder directly from config/app_config.yaml to avoid circular imports

def get_configured_data_folder():
    """Read data folder from config/app_config.yaml"""
    try:
        config_path = PROJECT_ROOT / "config" / "app_config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        data_folder = config.get("data_folder")
        if not data_folder:
            raise ValueError("'data_folder' not found in config/app_config.yaml")
        
        # Resolve relative/absolute path
        if os.path.isabs(data_folder):
            resolved_path = Path(data_folder)
        else:
            resolved_path = PROJECT_ROOT / data_folder
        
        print(f"[DEBUG] Configured data folder: {data_folder}")
        print(f"[DEBUG] Resolved to: {resolved_path}")
        return resolved_path
        
    except Exception as err:
        print(f"[WARN] Could not read data folder from config: {err}")
        return PROJECT_ROOT / "Data"

DATA_DIR = get_configured_data_folder()
print(f"[DEBUG] Final DATA_DIR: {DATA_DIR}")
print(f"[DEBUG] DATA_DIR exists: {DATA_DIR.exists()}")

OUTPUT_JSON = PROJECT_ROOT / "field_formats.json"
REPORT_CSV = PROJECT_ROOT / "FieldReport.csv"

# --------------------------- Helpers --------------------------- #

def detect_date_pattern(sample: str) -> str:
    """Infer a human-readable date pattern from a sample string."""
    sample = sample.strip()
    # YYYY-MM-DD or YYYY/MM/DD
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", sample):
        return "YYYY-MM-DD"
    # YYYYMMDD
    if re.fullmatch(r"\d{8}", sample):
        return "YYYYMMDD"
    # DD/MM/YYYY or MM/DD/YYYY
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", sample):
        first, second, _ = sample.split("/")
        # Heuristic: if first > 12 then DD/MM otherwise MM/DD
        try:
            if int(first) > 12:
                return "DD/MM/YYYY"
            else:
                return "MM/DD/YYYY"
        except ValueError:
            pass
    # YYYY/MM/DD
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", sample):
        return "YYYY/MM/DD"
    # DD-MM-YYYY or MM-DD-YYYY
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", sample):
        first, second, _ = sample.split("-")
        try:
            if int(first) > 12:
                return "DD-MM-YYYY"
            else:
                return "MM-DD-YYYY"
        except ValueError:
            pass
    # Fallback generic
    return "Unknown"


def classify_series(series: pd.Series) -> str:
    """Classify a pandas Series into a simple data type string.

    Returns:
        - "Integer", "Float", "Text" for non-date types
        - "Date[<pattern>]" e.g. "Date[YYYY-MM-DD]" when date detected.
    """
    clean_series = series.dropna()
    if clean_series.empty:
        return "Text"

    inferred = infer_dtype(clean_series, skipna=True)

    if inferred in {"integer", "mixed-integer", "integer-na", "mixed-integer-float"}:
        return "Integer"
    if inferred in {"floating", "floating-na"}:
        return "Float"

    # pandas sometimes keeps dates as object; attempt fallback parse
    is_date_like = False
    try:
        parsed = pd.to_datetime(clean_series.iloc[:20], errors="coerce")
        # if at least 70% of sample parsed successfully treat as date
        success_ratio = parsed.notna().mean() if len(parsed) else 0
        is_date_like = success_ratio >= 0.7
    except Exception:
        is_date_like = False

    if inferred.startswith("datetime") or inferred in {"date"} or is_date_like:
        sample_val = str(clean_series.iloc[0])
        pattern = detect_date_pattern(sample_val)
        return f"Date[{pattern}]"

    return "Text"


def analyze_csv(file_path: Path) -> tuple[Dict[str, Dict[str, str]], List[Dict[str, str]]]:
    """Read entire CSV and return:
    1. metadata dict mapping column -> {Format, PopulatedRows, Min, Max}
    2. list of row dicts suitable for report (with File key added later)"""

    try:
        # Read full CSV; for large files this may be heavy but enables accurate statistics
        df = pd.read_csv(file_path, low_memory=False)
    except Exception as exc:
        print(f"[WARN] Skipping {file_path.name}: {exc}")
        return {}, []

    metadata_rows: List[Dict[str, str]] = []

    # Basic row count for the file
    row_count = int(len(df))

    for idx, col in enumerate(df.columns, start=1):
        series = df[col]
        fmt = classify_series(series)

        # Basic stats
        populated = int(series.count())
        min_val: str = ""
        max_val: str = ""
        if fmt in {"Integer", "Float"}:
            try:
                min_val = str(series.min())
                max_val = str(series.max())
            except Exception:
                # In case min/max fails due to mixed types
                min_val = max_val = ""

        metadata_rows.append({
            "Column": col,
            "ColumnIndex": idx,
            "Format": fmt,
            "RowCount": row_count,
            "PopulatedRows": populated,
            "Min": min_val,
            "Max": max_val,
        })

    # Build metadata mapping structure
    metadata_mapping: Dict[str, Dict[str, str]] = {
        row["Column"]: {
            "ColumnIndex": row["ColumnIndex"],
            "Format": row["Format"],
            "RowCount": row["RowCount"],
            "PopulatedRows": row["PopulatedRows"],
            "Min": row["Min"],
            "Max": row["Max"],
        }
        for row in metadata_rows
    }

    return metadata_mapping, metadata_rows


def scan_all_csvs(data_dir: Path):
    """Walk through *data_dir* and build mapping and metadata rows."""
    results: Dict[str, Dict[str, str]] = {}
    all_metadata_rows: List[Dict[str, str]] = []

    for csv_file in data_dir.rglob("*.csv"):
        if any(part == "cache" for part in csv_file.parts):
            continue

        meta_mapping, metadata_rows = analyze_csv(csv_file)
        if meta_mapping:
            rel_path = str(csv_file.relative_to(data_dir))
            results[rel_path] = meta_mapping
            # Append file path to each metadata row
            for row in metadata_rows:
                row_with_file = {"File": rel_path, **row}
                all_metadata_rows.append(row_with_file)

    return results, all_metadata_rows


def diff_mappings(old: Dict[str, Dict[str, str]], new: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    """Compute differences between the *old* and *new* mappings.

    Returns a list of dict rows for CSV report."""
    rows: List[Dict[str, str]] = []
    all_files = set(old) | set(new)

    for file in sorted(all_files):
        old_cols = old.get(file, {})
        new_cols = new.get(file, {})
        # Columns present in both -> check for format changes
        for col in (set(old_cols) & set(new_cols)):
            if old_cols[col] != new_cols[col]:
                rows.append({
                    "File": file,
                    "Column": col,
                    "ChangeType": "Changed",
                    "OldFormat": old_cols[col],
                    "NewFormat": new_cols[col],
                })
        # Columns only in old -> removed
        for col in (set(old_cols) - set(new_cols)):
            rows.append({
                "File": file,
                "Column": col,
                "ChangeType": "Removed",
                "OldFormat": old_cols[col],
                "NewFormat": "",
            })
        # Columns only in new -> added
        for col in (set(new_cols) - set(old_cols)):
            rows.append({
                "File": file,
                "Column": col,
                "ChangeType": "Added",
                "OldFormat": "",
                "NewFormat": new_cols[col],
            })
    return rows


def save_json(data: Dict[str, Dict[str, str]], path: Path) -> None:
    path.write_text(json.dumps(data, indent=2))


def save_report(rows: List[Dict[str, str]], path: Path) -> None:
    if not rows:
        print("No changes detected. FieldReport.csv not created.")
        return
    # Create DataFrame for easy CSV writing
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    print(f"Field report saved to {path}")

# --------------------------- Main --------------------------- #

def main():
    if not DATA_DIR.exists():
        print(f"Data directory not found: {DATA_DIR}")
        return

    print(f"Scanning CSV files under {DATA_DIR}...")
    new_meta, metadata_rows = scan_all_csvs(DATA_DIR)

    if OUTPUT_JSON.exists():
        print(f"Existing JSON found: {OUTPUT_JSON}. Comparing...")
        old_meta_raw = json.loads(OUTPUT_JSON.read_text())
        # Support legacy simple-format JSON (column -> Format)
        def ensure_meta_structure(data):
            out = {}
            for file, colmap in data.items():
                out[file] = {}
                for col, info in colmap.items():
                    if isinstance(info, dict):
                        out[file][col] = info
                    else:
                        # Legacy: only Format string stored
                        out[file][col] = {
                            "Format": info,
                            "RowCount": "",
                            "PopulatedRows": "",
                            "Min": "",
                            "Max": "",
                        }
            return out

        old_meta = ensure_meta_structure(old_meta_raw)

        def diff_metadata(old, new):
            """Compare old vs new metadata including column index to detect moves/renames."""
            rows = []
            attrs = ["Format", "RowCount", "PopulatedRows", "Min", "Max"]

            all_files = set(old) | set(new)
            for file in all_files:
                old_cols = old.get(file, {})
                new_cols = new.get(file, {})

                # Build index->name maps
                old_by_idx = {info.get("ColumnIndex", ""): col for col, info in old_cols.items()}
                new_by_idx = {info.get("ColumnIndex", ""): col for col, info in new_cols.items()}

                all_indexes = set(old_by_idx) | set(new_by_idx)

                for idx in all_indexes:
                    old_name = old_by_idx.get(idx, "")
                    new_name = new_by_idx.get(idx, "")
                    old_info = old_cols.get(old_name) if old_name else None
                    new_info = new_cols.get(new_name) if new_name else None

                    # Determine change type
                    if old_name and not new_name:
                        change_type = "Removed"
                    elif new_name and not old_name:
                        change_type = "Added"
                    else:
                        change_type = "Unchanged"

                    changed_attr = False
                    row = {
                        "File": file,
                        "ColumnIndex": idx,
                        "OldColumn": old_name,
                        "NewColumn": new_name,
                        "ChangeType": change_type,
                    }

                    for a in attrs:
                        row[f"Old{a}"] = old_info.get(a, "") if old_info else ""
                        row[f"New{a}"] = new_info.get(a, "") if new_info else ""
                        if row[f"Old{a}"] != row[f"New{a}"]:
                            changed_attr = True

                    # Re-evaluate changetype
                    if change_type == "Unchanged" and changed_attr:
                        row["ChangeType"] = "Changed"

                    rows.append(row)

            return rows

        diff_rows = diff_metadata(old_meta, new_meta)
    else:
        print("No existing JSON found. Creating a new one.")
        diff_rows = []

    # Build final rows combining current metadata with diff information
    # Start with current metadata rows (latest run)
    meta_lookup = {(row["File"], row["ColumnIndex"]): row for row in metadata_rows}

    # Ensure latest run rows include prefix New* columns for uniformity
    for row in meta_lookup.values():
        row.setdefault("ChangeType", "Unchanged")
        for a in ["ColumnIndex", "Format", "RowCount", "PopulatedRows", "Min", "Max"]:
            row.setdefault(f"Old{a}", "")
            row.setdefault(f"New{a}", row.get(a, ""))

    # Overlay diff rows (which containt Old*/New* detail and ChangeType)
    for drow in diff_rows:
        key = (drow["File"], drow["ColumnIndex"])
        if key in meta_lookup:
            meta_lookup[key].update(drow)
        else:
            # Column removed case: create placeholder row
            placeholder = {
                "File": drow.get("File"),
                "Column": drow.get("NewColumn", ""),
                "ColumnIndex": drow.get("ColumnIndex", ""),
                "ColumnIndex": "",
                "Format": "",
                "RowCount": "",
                "PopulatedRows": "",
                "Min": "",
                "Max": "",
            }
            placeholder.update(drow)
            meta_lookup[key] = placeholder

    final_rows = list(meta_lookup.values())

    # Always save report now
    save_report(final_rows, REPORT_CSV)

    save_json(new_meta, OUTPUT_JSON)
    print(f"Data formats saved to {OUTPUT_JSON}")

    if not OUTPUT_JSON.exists():
        print("Warning: Failed to write JSON output.")

if __name__ == "__main__":
    main() 