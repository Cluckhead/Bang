# Unit Testing Implementation Plan

- **Always update Docs/Tests.md with details of each test implemented and what it is testing.**  


This plan outlines the steps to introduce comprehensive unit testing to the Simple Data Checker application using the `pytest` framework.

## Phase 1: Setup and Foundation

### Step 1.1: Install Testing Framework

- **Action:** Add `pytest` and `pytest-cov` (for coverage) to your development dependencies. (Complete)
- **Command:** `pip install pytest pytest-cov pytest-mock` (or add to `requirements-dev.txt`). (Complete)
- **Target:** Project dependencies. (Complete)
    

### Step 1.2: Create Testing Directory Structure

- **Action:** Create a dedicated `tests/` directory at the root of your project. (Complete)
- **Action:** Inside `tests/`, create subdirectories mirroring your main application structure (e.g., `tests/views/`, `tests/utils/`, `tests/processing/`). (Complete)
- **Action:** Add an empty `__init__.py` file to the `tests/` directory and each subdirectory to make them recognizable as Python packages. (Complete)
- **Target:** Project file structure. (Complete)
    
### Step 1.3: Initial pytest Configuration

- **Action:** Create a `pytest.ini` file in the project root. (Complete)
- **Content:**
    
    ```
    [pytest]
    minversion = 6.0
    testpaths = tests
    python_files = test_*.py
    addopts = -ra -q --cov=. --cov-report=html
    ```
    
- **Target:** `pytest.ini` (new file). (Complete)


### Step 1.4: Basic Flask App Fixture

- **Action:** Create a `tests/conftest.py` file.
- **Action:** Implement a `pytest` fixture that creates and configures a test instance of the Flask application using the `create_app` factory from `app.py`. This fixture will provide the necessary application context for testing views and components that rely on `current_app`.
    
- **Action:** Implement a fixture for the Flask test client (`app.test_client()`).
- **Target:** `tests/conftest.py` (new file).
    

## Phase 2: Testing Core Utilities and Logic

### Step 2.1: Test Utility Functions (`utils.py`)

- **Action:** Create `tests/utils/test_utils.py`. (Complete)
- **Action:** Write tests for `_is_date_like`, covering various valid and invalid date string formats.
- **Action:** Write tests for `parse_fund_list`, covering valid inputs, empty inputs, malformed inputs, and inputs with varying spacing.
- **Action:** Write tests for `get_data_folder_path`. Mock `config.DATA_FOLDER` and `os.getcwd()`/`os.path.isdir()`/`os.path.isabs()` using `pytest-mock` (`mocker` fixture) to test different scenarios (config set, config missing, relative path, absolute path, path doesn't exist). (Complete)
- **Action:** Write tests for `load_exclusions`. Mock file system interactions (`os.path.exists`, `pd.read_csv`) to test file not found, empty file, valid file scenarios.
- **Action:** Write tests for `load_weights_and_held_status`. Mock file system (`pd.read_csv`), test different file formats (wide vs. long), missing columns, date parsing variations, and calculation logic.
- **Action:** Write tests for `replace_nan_with_none`. Test with nested dictionaries, lists, various data types including `np.nan` and `pd.NA`.
- **Target:** `tests/utils/test_utils.py` (new file). (Complete)

### Step 2.2: Test Configuration Loading (`config.py`)

- **Action:** Create `tests/config/test_config.py`. (Complete)
- **Action:** Write simple tests to verify that expected configuration variables exist and have the correct basic types (e.g., `COLOR_PALETTE` is a list, `COMPARISON_CONFIG` is a dict). This is less about testing Python's import and more about ensuring config structure is maintained. (Complete)
    
- **Target:** `tests/config/test_config.py` (new file). (Complete)
    

### Step 2.3: Test Standalone Processing Logic

- **Action:** Create test files for modules containing logic usable _without_ a full Flask app context (mocking file I/O where necessary). (Complete)
- **Action:** (`tests/processing/test_metric_calculator.py`): Test `_calculate_column_stats` and `calculate_latest_metrics`. Provide sample DataFrames (created directly or loaded from test CSVs using mocked `pd.read_csv`), test calculations, NaN handling, and edge cases (e.g., single data point, zero standard deviation). Mock `load_and_process_data` if testing the main function directly. (Complete)
- **Action:** (`tests/processing/test_curve_processing.py`): Test `_term_to_days`, `load_curve_data` (mock `pd.read_csv`), `get_latest_curve_date`, and `check_curve_inconsistencies`. Use sample DataFrames to test inconsistency detection logic (monotonicity, anomaly checks). (Complete)
- **Action:** (`tests/processing/test_issue_processing.py`): Test `load_issues`, `_generate_issue_id`, `add_issue`, `close_issue`, `load_fund_list`. Mock file I/O (`os.path.exists`, `pd.read_csv`, `df.to_csv`). Test ID generation logic, adding/closing issues, and file handling. (Complete)
- **Action:** (`tests/processing/test_staleness_processing.py`): Test `is_placeholder_value`, `get_staleness_summary`, `get_stale_securities_details`. Mock file I/O and test detection logic with various data patterns. (Complete)
- **Action:** (`tests/processing/test_attribution_processing.py`): Test `sum_l2s_block`, `sum_l1s_block`, `compute_residual_block`, `calc_residual`, `norm`. Use sample DataFrames/rows. (Complete)
- **Target:** New test files in `tests/processing/`. (Complete)

## Phase 3: Testing Data Loading and File Processing

### Step 3.1: Test Data Loader (`data_loader.py`)

- **Action:** Create `tests/processing/test_data_loader.py`. (Complete)
- **Action:** Test helper functions: `_find_column`, `_create_empty_dataframe`, `_find_columns_for_file`, `_parse_date_column`, `_convert_value_columns`. Use sample column lists and DataFrames. (Complete)
- **Action:** Test `_process_single_file`. Mock `pd.read_csv` and `os.path.exists`. Provide mock CSV content (using `io.StringIO`) representing different scenarios: missing columns, date format variations, non-numeric values, empty files. Verify the returned DataFrame structure, column names, data types, and index. (Complete)
    
- **Action:** Test `load_and_process_data`. Mock `_process_single_file` or mock file system interactions. Test loading primary only vs. primary and secondary files. Test error handling when files are missing or processing fails. Use the app context fixture if testing the part that reads `current_app.config['DATA_FOLDER']`. (Complete)
- **Target:** `tests/processing/test_data_loader.py` (new file). (Complete)
    
### Step 3.2: Test Security Processing (`security_processing.py`)

- **Action:** Create `tests/processing/test_security_processing.py`. (Complete)
- **Action:** Test `load_and_process_security_data`. Mock `pd.read_csv`. Provide mock wide-format CSV content. Test column identification (ID, static, date), melting process, date parsing, NaN handling, and index setting. Test the caching mechanism. (Complete)
    
- **Action:** Test `calculate_security_latest_metrics`. Provide sample long-format DataFrames (output from the previous function). Test metric calculations (latest value, change, Z-score, mean, max, min), handling of missing data for latest date, and preservation of static columns. (Complete)
- **Target:** `tests/processing/test_security_processing.py` (new file). (Complete)

### Step 3.3: Test File Processors (`process_data.py`, `weight_processing.py`)

- **Action:** Create `tests/processing/test_process_data.py`. (Complete)
- **Action:** Refactor `process_data.py`'s `process_csv_file` and helper functions (`replace_headers_with_dates`, `aggregate_data`) to be more easily testable if needed (e.g., reduce reliance on global state or side effects). (Complete)
    
- **Action:** Write tests for `replace_headers_with_dates` and `aggregate_data`. Provide sample DataFrames and mock `Dates.csv` data. Verify header replacement logic and data aggregation rules (fund merging, ISIN suffixing). Mock file I/O (`pd.read_csv`, `df.to_csv`). (Complete)
    
- **Action:** Create `tests/processing/test_weight_processing.py`. (Complete)
- **Action:** Test `process_weight_file`. Mock file I/O (`pd.read_csv`, `df.to_csv`). Provide sample weight files (`pre_w_*.csv`) and a mock `Dates.csv`. Verify header replacement, date sorting, and output format for different weight file types (funds, bench, secs). Test dynamic metadata detection for `w_secs`. (Complete)
    
- **Target:** New test files in `tests/processing/`. (Complete)

## Phase 4: Testing Flask Views and API Endpoints

### Step 4.1: Test Main Views (`main_views.py`)

- **Action:** Create `tests/views/test_main_views.py`.
- **Action:** Use the test client fixture (`client`).
- **Action:** Test the `/` route (`index` function). Mock `load_and_process_data` and `calculate_latest_metrics` to return controlled data. Verify the response status code (200). Verify that the correct template (`index.html`) is rendered. Check the context passed to the template (e.g., `metrics`, `summary_data`, `summary_metrics`).
    
- **Target:** `tests/views/test_main_views.py` (new file).
    

### Step 4.2: Test Metric Views (`metric_views.py`)

- **Action:** Create `tests/views/test_metric_views.py`.
- **Action:** Test the `/metric/<metric_name>` route (`metric_page` function). Mock data loading and metric calculation. Test with valid and invalid metric names. Test scenarios with and without secondary data (`sp_` files). Verify response code, template rendering, and context variables (`metric_name`, `charts_data_json`, `latest_date`, `missing_funds`).
    
- **Target:** `tests/views/test_metric_views.py` (new file).
    
### Step 4.3: Test Security Views (`security_views.py`)

- **Action:** Create `tests/views/test_security_views.py`.
- **Action:** Test `/security/summary` (`securities_page`). Mock data loading/metric calculation. Test pagination logic (requesting different `page` args). Test filtering (passing `filter_` args). Test sorting (passing `sort_by`, `sort_order` args). Test search (passing `search_term`). Verify response code, template, and context (pagination object, table data, filter options, active filters, sort state).
    
- **Action:** Test `/security/details/<metric_name>/<path:security_id>` (`security_details`). Mock data loading. Test with valid and invalid IDs (including those with special characters). Verify response code, template, and context (`security_id`, `metric_name`, `chart_data_json`, `static_info`).
- **Target:** `tests/views/test_security_views.py` (new file).

### Step 4.4: Test Comparison Views (`generic_comparison_views.py`)

- **Action:** Create `tests/views/test_generic_comparison_views.py`.
- **Action:** Test `/compare/<comparison_type>/summary`. Mock `load_generic_comparison_data`, `calculate_generic_comparison_stats`, `load_weights_and_held_status`. Test for different `comparison_type` values. Test filtering, sorting, pagination, and the `show_sold` toggle. Verify template and context.
- **Action:** Test `/compare/<comparison_type>/details/<path:security_id>`. Mock data loading and stats calculation. Test with valid/invalid IDs. Verify template and context, including `chart_data` and `holdings_data`.
- **Target:** `tests/views/test_generic_comparison_views.py` (new file).
    

### Step 4.5: Test Other View Blueprints

- **Action:** Create corresponding test files (e.g., `test_fund_views.py`, `test_exclusion_views.py`, `test_issue_views.py`, `test_curve_views.py`, `test_attribution_views.py`, `test_staleness_views.py`, `test_weight_views.py`) in `tests/views/`.
- **Action:** For each blueprint, test its routes using the test client.
- **Action:** Mock underlying data loading and processing functions specific to each view.
- **Action:** Verify response codes, template rendering, context variables, redirects, and flash messages where applicable.
- **Action:** For views handling POST requests (e.g., adding exclusions, closing issues), simulate form submissions using `client.post()` with `data={...}` and `follow_redirects=True`.

- **Target:** New test files in `tests/views/`.
    

### Step 4.6: Test API Endpoints (`api_views.py`, `api_routes_call.py`, `