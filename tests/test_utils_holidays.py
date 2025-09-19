# Purpose: Simple tests for holiday checker to ensure safe behavior with missing file.

from core.utils import check_holidays


def test_check_holidays_missing_file(tmp_path):
    res = check_holidays(str(tmp_path))
    assert isinstance(res, dict)
    assert res["has_holiday_today"] is False

