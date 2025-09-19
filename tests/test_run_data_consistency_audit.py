# Purpose: Test data_audit.run_data_consistency_audit detects mismatched date ranges across ts_ files.

import pandas as pd
from data_processing.data_audit import run_data_consistency_audit


def _write_ts(tmp_path, fname, dates):
    rows = [f"{d},F1,1.0" for d in dates]
    csv_content = "Date,Code,Value\n" + "\n".join(rows)
    f = tmp_path / fname
    f.write_text(csv_content)


def test_run_data_consistency_audit_mismatch(tmp_path):
    # File 1 covers two dates, File 2 covers one overlapping and one new date
    _write_ts(tmp_path, "ts_A.csv", ["2024-01-01", "2024-01-02"])
    _write_ts(tmp_path, "ts_B.csv", ["2024-01-02", "2024-01-03"])

    report = run_data_consistency_audit(str(tmp_path))

    assert not report["ts_files"]["all_match"], "Expected date ranges not to match."
    # Ensure offending filenames listed in summary or details
    assert "ts_A.csv" in report["file_details"] and "ts_B.csv" in report["file_details"]
