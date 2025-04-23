# Purpose: Tests the API endpoints for data retrieval, API calls, reruns, and scheduling in the Simple Data Checker app.
import pytest
import os
import json
import pandas as pd
from unittest.mock import patch

def create_dummy_fundlist(data_folder_path, filename="FundList.csv"):
    """Helper to create a dummy FundList.csv file."""
    file_path = os.path.join(data_folder_path, filename)
    df = pd.DataFrame({
        'Fund Code': ['FUND1', 'FUND2'],
        'Total Asset Value USD': [1000, 2000],
        'Picked': [True, False]
    })
    df.to_csv(file_path, index=False)
    return file_path

def create_dummy_querymap(data_folder_path, filename="QueryMap.csv"):
    """Helper to create a dummy QueryMap.csv file."""
    file_path = os.path.join(data_folder_path, filename)
    df = pd.DataFrame({
        'QueryID': ['Q1', 'Q2'],
        'FileName': ['ts_MetricA.csv', 'ts_MetricB.csv']
        # Add other columns expected by the view logic if necessary
    })
    df.to_csv(file_path, index=False)
    return file_path

class TestApiViews:
    def test_get_data_page_success(self, client, mocker):
        data_folder = client.application.config['DATA_FOLDER']
        create_dummy_fundlist(data_folder)
        
        # Keep mocks for now, but the file exists if needed
        mocker.patch('os.path.exists', return_value=True) 
        fund_df = pd.DataFrame([
            {'Fund Code': 'FUND1', 'Total Asset Value USD': 1000, 'Picked': True}
        ])
        mocker.patch('pandas.read_csv', return_value=fund_df) 
        mocker.patch('views.api_routes_data.get_data_file_statuses', return_value={})
        response = client.get('/get_data')
        assert response.status_code == 200
        assert b'get_data' in response.data or b'Fund' in response.data
        # TODO: Add more checks for template context

    def test_get_data_page_missing_file(self, client, mocker):
        mocker.patch('os.path.exists', return_value=False)
        response = client.get('/get_data')
        assert response.status_code == 500
        assert b'FundList.csv not found' in response.data

    def test_run_api_calls_success(self, client, mocker):
        data_folder = client.application.config['DATA_FOLDER']
        create_dummy_querymap(data_folder)
        
        # Keep mocks, file exists
        mocker.patch('os.path.exists', return_value=True) 
        query_map_df = pd.DataFrame([
            {'QueryID': 'Q1', 'FileName': 'ts_test.csv'}
        ])
        mocker.patch('pandas.read_csv', return_value=query_map_df) 
        mocker.patch('views.api_routes_call._simulate_and_print_tqs_call', return_value=5)
        data = {
            'date_mode': 'quick',
            'write_mode': 'expand',
            'days_back': 5,
            'end_date': '2023-01-10',
            'funds': ['FUND1']
        }
        response = client.post('/run_api_calls', data=json.dumps(data), content_type='application/json')
        assert response.status_code == 200
        resp_json = response.get_json()
        assert resp_json['status'] in ('completed', 'completed_with_errors')
        assert 'summary' in resp_json
        # TODO: Add more checks for summary content

    def test_rerun_api_call_success(self, client, mocker):
        data_folder = client.application.config['DATA_FOLDER']
        create_dummy_querymap(data_folder)
        
        # Keep mocks, file exists
        mocker.patch('os.path.exists', return_value=True) 
        query_map_df = pd.DataFrame([
            {'QueryID': 'Q1', 'FileName': 'ts_test.csv'}
        ])
        mocker.patch('pandas.read_csv', return_value=query_map_df) 
        mocker.patch('views.api_routes_call._simulate_and_print_tqs_call', return_value=3)
        data = {
            'query_id': 'Q1',
            'days_back': 3,
            'end_date': '2023-01-10',
            'funds': ['FUND1'],
            'overwrite_mode': False
        }
        response = client.post('/rerun-api-call', data=json.dumps(data), content_type='application/json')
        assert response.status_code == 200
        resp_json = response.get_json()
        assert resp_json['status'] in ('Simulated OK', 'Saved OK', 'Saved OK (Empty)')
        # TODO: Add more checks for returned data

    def test_list_schedules_empty(self, client, mocker):
        mocker.patch('views.api_routes_call.load_schedules', return_value=[])
        response = client.get('/schedules')
        assert response.status_code == 200
        assert response.get_json() == []

    def test_add_schedule_success(self, client, mocker):
        mocker.patch('views.api_routes_call.load_schedules', return_value=[])
        mocker.patch('views.api_routes_call.save_schedules')
        data = {
            'schedule_time': '2023-01-15T10:00',
            'write_mode': 'expand',
            'date_mode': 'quick',
            'funds': ['FUND1'],
            'days_back': 5
        }
        response = client.post('/schedules', data=json.dumps(data), content_type='application/json')
        assert response.status_code == 201
        resp_json = response.get_json()
        assert resp_json['schedule_time'] == '2023-01-15T10:00'
        assert resp_json['date_mode'] == 'quick'
        # TODO: Add more checks for returned schedule

    def test_delete_schedule_success(self, client, mocker):
        mocker.patch('views.api_routes_call.load_schedules', return_value=[{'id': 1}])
        mocker.patch('views.api_routes_call.save_schedules')
        response = client.delete('/schedules/1')
        assert response.status_code == 204

    def test_delete_schedule_not_found(self, client, mocker):
        mocker.patch('views.api_routes_call.load_schedules', return_value=[{'id': 1}])
        response = client.delete('/schedules/2')
        assert response.status_code == 404
        assert b'Schedule not found' in response.data

# TODO: Add more edge case and error scenario tests for all endpoints 