# Purpose: Contains tests for the fund views blueprint (views/fund_views.py).
import pytest
import pandas as pd
import re
import json

SAMPLE_FUND_CODE = 'FUND123'
SAMPLE_METRIC_FILES = ['ts_metric1.csv', 'ts_metric2.csv']
SAMPLE_METRIC_NAMES = ['Metric1', 'Metric2']

@pytest.fixture
def mock_fund_detail_logic(mocker):
    # Mock glob.glob to return fake ts_*.csv files
    mocker.patch('views.fund_views.glob.glob', return_value=SAMPLE_METRIC_FILES)
    # Mock os.path.exists to always return True
    mocker.patch('views.fund_views.os.path.exists', return_value=True)
    # Mock load_and_process_data to return a DataFrame with the fund code in the index
    def fake_load_and_process_data(primary_filename, data_folder_path):
        df = pd.DataFrame({'Value': [1, 2]}, index=pd.MultiIndex.from_tuples(
            [(SAMPLE_FUND_CODE, pd.Timestamp('2023-01-01')), (SAMPLE_FUND_CODE, pd.Timestamp('2023-01-02'))],
            names=['Code', 'Date']
        ))
        return (df, ['Value'], None)
    mocker.patch('views.fund_views.load_and_process_data', side_effect=fake_load_and_process_data)
    return

def test_fund_detail_page_success(client, mock_fund_detail_logic):
    response = client.get(f"/fund/{SAMPLE_FUND_CODE}")
    assert response.status_code == 200
    assert f"Fund Details: {SAMPLE_FUND_CODE}".encode() in response.data
    # Extract chart data JSON from the script tag
    match = re.search(rb'<script id="fundChartData" type="application/json">\s*(.*?)\s*</script>', response.data, re.DOTALL)
    assert match, "Chart data JSON script tag not found in response."
    chart_data_json = match.group(1)
    chart_data = json.loads(chart_data_json)
    metric_names_in_chart = [c['metricName'] for c in chart_data]
    for metric in SAMPLE_METRIC_NAMES:
        assert metric in metric_names_in_chart 