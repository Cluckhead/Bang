# Purpose: Minimal test for data_loader._find_columns_for_file on security-style headers.

from core.data_loader import _find_columns_for_file


def test_find_columns_for_file_security_like():
    header = [
        "ISIN",
        "Code",
        "Security Name",
        "Type",
        "Currency",
        "2024-01-01",
        "2024-01-02",
    ]
    date_col, code_col, bm_present, bm_col, fund_val_cols, scope_col = _find_columns_for_file(
        header, "sec_Spread.csv"
    )
    # For wide security files, code_col may be None; date_col likely None; fund_val_cols should include date-like columns
    assert isinstance(fund_val_cols, list)

