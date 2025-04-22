# Code Improvement Plan

## Phase 1: Foundational Refactoring & Cleanup

### Step 1.1: Centralize Logging
- **1.1.1** (`app.py`): Finalize centralized logging in `create_app` with `app.logger`, `RotatingFileHandler`, and `StreamHandler`. [complete]
- **1.1.2**: Remove standalone logging setups (e.g., `logging.basicConfig`, manual handlers) from:
  - `metric_calculator.py`
  - `process_data.py`
  - `process_weights.py`
  - `process_w_secs.py`
  - `security_processing.py` [complete]
- **1.1.3**: Replace all `print()` debug/log statements with logger calls (`current_app.logger` or `logging.getLogger(__name__).<level>`) in: [complete]
  - `app.py`, `curve_processing.py`, `issue_processing.py`, `metric_calculator.py`, `process_data.py`, `process_weights.py`, `process_w_secs.py`, `security_processing.py`
  - All view modules under `views/` (e.g., `api_core.py`, `api_routes_*`, `attribution_views.py`, `comparison_views.py`, etc.)
  - `weight_processing.py`

### Step 1.2: Centralize Configuration Access [complete]
- **1.2.1**: Find direct imports of `DATA_FOLDER` in:
  - `issue_processing.py`
  - `process_weights.py` *(uses `current_dir`)*
  - `process_w_secs.py` *(uses `current_dir`)*
- **1.2.2**: Refactor these modules (and related utilities like `load_exclusions`, `load_available_securities`, etc.) to accept `data_folder_path` as a function argument.
- **1.2.3**: Update view functions (e.g., `views/issue_views.py`) to pull `current_app.config['DATA_FOLDER']` and pass it to processing functions. Update `main()` in data scripts to use `utils.get_data_folder_path`.
- **1.2.4**: Move configuration values to `config.py`:
  - `DATA_SOURCES` list from `views/issue_views.py`
  - Thresholds `-0.5`, `3`, `0.2` from `curve_processing.py` [complete]
- **1.2.5**: Update code in `views/issue_views.py` and `curve_processing.py` to read these values from `current_app.config`. [complete]

### Step 1.3: Refactor Utilities (DRY Principle) [complete]
- **1.3.1**: Consolidate `_is_date_like` logic by importing it from `utils` in:
  - `views/attribution_views.py`, `comparison_views.py`, `duration_comparison_views.py`, `spread_duration_comparison_views.py`, `weight_processing.py`, `views/weight_views.py`
- **1.3.2**: Move `replace_nan_with_none` from `views/security_views.py` to `utils.py` and update imports.
- **1.3.3**: Define `load_weights_and_held_status` in `utils.py` (parameterize `data_folder_path` and `id_col_override`), based on code in `views/comparison_views.py`.
- **1.3.4**: Update comparison view modules to use `utils.load_weights_and_held_status`.

## Phase 2: Major Refactoring

### Step 2.1: Refactor Weight/Data Processing Logic [complete]
- **2.1.1** (`weight_processing.py`): Enhance `process_weight_file` to handle `w_Funds.csv`, `w_Bench.csv`, `w_secs.csv`; detect metadata columns dynamically and sort dates; accept absolute paths. [complete]
- **2.1.2** (`process_data.py`): Refactor `process_csv_file` to separate header handling and data aggregation, and simplify header replacements. [complete]
- **2.1.3**: Ensure `process_data.py` `main()` calls `weight_processing.process_weight_file` for `pre_w_*.csv` files. [complete]
- **2.1.4**: Remove redundant scripts: `process_w_secs.py`, `process_weights.py`. [complete]
- **2.1.5**: Verify `main()` uses `utils.get_data_folder_path`. [complete]

### Step 2.2: Refactor Comparison Views
- **2.2.1**: Create `views/comparison_helpers.py` with functions for:
  - Loading and merging comparison files.
  - Calculating comparison statistics.
  - Handling filtering, sorting, and pagination.
- **2.2.2**: Refactor `views/comparison_views.py`, `views/duration_comparison_views.py`, `views/spread_duration_comparison_views.py` to use these helpers.

### Step 2.3: Refactor Complex Functions
- **2.3.1** (`data_loader.py`): Break `_process_single_file` into smaller helpers (`_find_columns_for_file`, `_parse_date_column`, `_convert_value_columns`).
- **2.3.2** (`views/api_routes_call.py`): Refactor `run_api_calls` into `_fetch_data_for_query`, `_validate_fetched_data`, and `_save_or_merge_data`.
- **2.3.3** Create `attribution_processing.py`.
- **2.3.4** (`views/attribution_views.py`): Move `compute_residual` and L1/L2 aggregation to `attribution_processing.py`.
- **2.3.5** (`views/attribution_views.py`): Update the view functions (attribution_summary, attribution_charts, attribution_radar, attribution_security_page) to import and call the functions from attribution_processing.py.

## Phase 3: Enhancements and File-Specific Improvements

### Step 3.1: Implement Data Validation
- **3.1.1**: (data_validation.py) Define specific validation rules/schemas (e.g., using simple pandas checks or exploring Pandera) for key file types: ts_*.csv, sec_*.csv, w_Funds.csv, w_Bench.csv, w_secs.csv, att_factors.csv, curves.csv, exclusions.csv, FundList.csv, QueryMap.csv. Focus on required columns, data types, and potential consistency rules.
- **3.1.2**: (views/api_routes_call.py) In the run_api_calls function, after successfully fetching data using the real API (_fetch_real_tqs_data) and before saving/merging, call validate_data from data_validation.py.
- **3.1.3: (views/api_routes_call.py) Update the results_summary dictionary based on the is_valid and errors returned by validate_data. Potentially prevent saving invalid data or save it with a warning status

### Step 3.2.1: Add Type Hinting
- Add type hints for function arguments and return types across all Python modules in the project.
    - app.py
    - config.py
    - curve_processing.py
    - data_loader.py
    - data_validation.py
    - issue_processing.py
    - metric_calculator.py
    - process_data.py
    - security_processing.py
    - utils.py
    - weight_processing.py
    - views/__init__.py
    - views/api_core.py
    - views/api_routes_call.py
    - views/api_routes_data.py
    - views/api_views.py
    - views/attribution_views.py
    - views/comparison_helpers.py (created in Step 2.2)
    - views/comparison_views.py
    - views/curve_views.py
    - views/duration_comparison_views.py
    - views/exclusion_views.py
    - views/fund_views.py
    - views/issue_views.py
    - views/main_views.py
    - views/metric_views.py
    - views/security_views.py
    - views/spread_duration_comparison_views.py
    - views/weight_views.py
    - attribution_processing.py



### Step 3.3: Improve Error Handling
- **Step 3.3.1**: Review file operations (pd.read_csv, df.to_csv, os.path.exists, os.path.join, etc.) in all .py files listed in Step 3.2.1. Ensure they are within robust try...except blocks, catching specific exceptions like FileNotFoundError, pd.errors.EmptyDataError, pd.errors.ParserError, KeyError, PermissionError, OSError. Log informative messages in except blocks.
- **Step 3.3.2**: (views/api_core.py) Enhance _fetch_real_tqs_data to catch specific API-related exceptions (e.g., connection errors, timeouts, authentication errors if applicable when the real API is added).
- **Step 3.3.3**: (views/exclusion_views.py) Modify remove_exclusion to write the filtered DataFrame to a temporary file first, then use os.replace to atomically replace the original exclusions.csv. Ensure the temporary file is cleaned up in case of errors (using try...finally).

### Step 3.4: Documentation and Cleanup
- **3.4.1**: Review and update docstrings and inline comments for all refactored code listed in step 3.2.1
- **3.4.2**: Verify `if __name__ == '__main__'` blocks in scripts:
  - `curve_processing.py`, `data_loader.py`, `data_validation.py`, `process_data.py`, `weight_processing.py`, `utils.py`
- **3.4.3**: Update `requirements.txt` and `README.md` to reflect dependency and file structure changes.

### Step 3.5: Minor File-Specific Suggestions
- **3.5.1**: Load `SECRET_KEY` from environment in `app.py`.
- **3.5.2**: Move hardcoded thresholds in `curve_processing.py` to `config.py`.
- **3.5.3**: Ensure `issue_processing.py` uses `current_app.logger` and receives `DATA_FOLDER`.
- **3.5.4**: Optimize data loading in `views/security_views.py`.
- **3.5.5**: Use `utils._is_date_like` and clarify weight formats in `views/weight_views.py`.
- **3.5.6**: Make file/column names configurable in `views/fund_views.py` and relocate date filtering.