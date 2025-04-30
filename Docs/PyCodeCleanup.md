# PHASE 1: Setup & Foundational Improvements (Low Disruption)

## 1.1 Dependency Management

**1.1.1**  Activate your project's virtual environment. [Complete]

**1.1.2**  Run the command `pip freeze > requirements.txt` in your terminal at the project root to generate a list of all installed Python packages and their exact versions.

**1.1.3**  Create a `requirements-dev.txt` file. [Complete]

**1.1.4**  Move testing-specific dependencies (like `pytest`, `pytest-cov`, `pytest-mock`) from `requirements.txt` to `requirements-dev.txt`.

**1.1.5**  Add `requirements.txt` and `requirements-dev.txt` to your version control system (e.g., Git).

## 1.2 Code Style & Linting

**1.2.1**  Add `black` and `flake8` to your `requirements-dev.txt`. [complete]

**1.2.2**  Install the development requirements: `pip install -r requirements-dev.txt`. [Complete]

**1.2.3**  Create a `pyproject.toml` file in the project root (if it doesn't exist).

**1.2.4**  Configure Black in `pyproject.toml` (e.g., specify line length if different from default 88):

```toml
[tool.black]
line-length = 88
```

**1.2.5**  Configure Flake8 in a `.flake8` file in the project root (or `pyproject.toml`). Start with defaults and potentially increase `max-line-length`:

```ini
[flake8]
max-line-length = 88
ignore = E203, W503 # Example ignores (Whitespace before ':', line break before binary operator)
```

**1.2.6**  Run `black .` from the project root to automatically format all Python files according to Black's style.

**1.2.7**  Run `flake8 .` from the project root to identify style violations and potential code issues.

**1.2.8**  Address the violations reported by Flake8 by modifying the code or adjusting the Flake8 configuration (e.g., adding specific ignores if necessary).

**1.2.9**  Commit the formatted code and configuration files (`pyproject.toml`, `.flake8`) to version control.

**1.2.10** Consider adding `black` and `flake8` checks to a pre-commit hook or CI/CD pipeline to maintain style consistency automatically.

## 1.3 Improve Test Suite Setup

**1.3.1**  (Fix Test Config Loading) In `tests/views/conftest.py`, locate the `app` fixture.

**1.3.2**  (Fix Test Config Loading) Immediately after the `app = Flask(...)` line within the `app` fixture, add `app.config.from_object('config')` to explicitly load the application's configuration.

**1.3.3**  (Fix Test Config Loading) Rerun `pytest` and confirm the `KeyError: 'COLOR_PALETTE'` previously observed in `tests/views/test_fund_views.py` is resolved.

**1.3.4**  (Fix Test Data Paths) In `tests/views/test_api_views.py`, identify tests requiring `FundList.csv` or `QueryMap.csv`.

**1.3.5**  (Fix Test Data Paths) Modify the setup for these tests (or create fixtures in `tests/views/conftest.py`) to use the `setup_data_folder` fixture's path (implicitly provided via `client.application.config['DATA_FOLDER']`) and create necessary dummy versions of `FundList.csv` and `QueryMap.csv` within that temporary directory using `create_dummy_fundlist` and `create_dummy_querymap` helpers.

**1.3.6**  (Fix Test Data Paths) In `tests/processing/test_weight_processing.py`, identify tests requiring `Dates.csv`.

**1.3.7**  (Fix Test Data Paths) Modify the `create_temp_csv` helper or test setup to use the `tmp_path` fixture provided by pytest (as already done) to create a dummy `Dates.csv` within the test's temporary directory. Ensure `process_weight_file` is called with the correct path to this dummy file.

**1.3.8**  (Fix Test Data Paths) Review `tests/processing/test_process_data.py` for similar `Dates.csv` dependencies and apply the fix from step 1.3.7.

**1.3.9**  (Standardize Data Paths) Review all test files (`tests/**/*.py`). If any test directly mocks `config.DATA_FOLDER` or uses hardcoded relative paths for data files *and* uses the `app` or `client` fixture, remove the direct mocking and rely on `client.application.config['DATA_FOLDER']` set by the `app` fixture in `tests/views/conftest.py`.

**1.3.10** (Standardize Data Paths) Review application code (`utils.py`, `views/**/*.py`, `*.py` at root) to ensure data folder paths are consistently retrieved via `current_app.config['DATA_FOLDER']` or the `get_data_folder_path` utility, rather than hardcoded relative paths or `os.getcwd()`. Refactor `get_data_folder_path` to prioritize `current_app.config['DATA_FOLDER']` if available within an app context.

**1.3.11** (Fix Test Data Paths) Rerun `pytest` and confirm `FileNotFoundError` logs related to `FundList.csv`, `QueryMap.csv`, and `Dates.csv` are resolved.

**1.3.12** (Fix Test Data Paths) Confirm warnings related to `app_root_path` in `utils.get_data_folder_path` are gone when tests are run within the app context provided by fixtures.

**1.3.13** (Reduce Log Noise) In `pytest.ini`, change the `--log-file-level` option from `INFO` to `WARNING` to make the log file cleaner.

**1.3.14** (Address Test Warnings - Curve) Add specific test cases to `tests/processing/test_curve_processing.py` for invalid terms (e.g., 'BAD', '', None) passed to `curve_processing._term_to_days` and assert that the function returns `None`.

**1.3.15** (Address Test Warnings - Weights) In `tests/processing/test_weight_processing.py`, add test cases with mismatched date counts vs. data column counts to explicitly test the truncation logic and confirm the logged warnings are expected behavior in those scenarios.

---

# PHASE 2: Code Improvements (Typing, Constants, Specific Error Handling)

## 2.1 Consistent Typing

**2.1.1** Add type hints to `utils._is_date_like(column_name: str) -> bool:`.

**2.1.2** Add type hints to `utils.parse_fund_list(fund_string: str) -> list:`.

**2.1.3** Add type hints to `utils.get_data_folder_path(app_root_path: Optional[str] = None) -> str:`.

**2.1.4** Add type hints to `utils.load_exclusions(exclusion_file_path: str) -> Optional[pd.DataFrame]:`.

**2.1.5** Add type hints to `utils.load_weights_and_held_status(data_folder: str, weights_filename: str = 'w_secs.csv', id_col_override: str = 'ISIN') -> pd.Series:`.

**2.1.6** Add type hints to `utils.replace_nan_with_none(obj: Any) -> Any:`.

**2.1.7** Add type hints to `utils.load_fund_groups(data_folder: str, fund_groups_filename: str = 'FundGroups.csv') -> dict:`.

**2.1.8** Add type hints to `config.py` variables where applicable (e.g., `COLOR_PALETTE: List[str]`, `COMPARISON_CONFIG: Dict[str, Dict[str, str]]`).

**2.1.9** Add type hints to `data_loader.load_simple_csv(filepath: str, filename_for_logging: str) -> Optional[pd.DataFrame]:`.

**2.1.10** Add type hints to `data_loader._find_column(...) -> str:`.

**2.1.11** Add type hints to `data_loader._create_empty_dataframe(...) -> pd.DataFrame:`.

**2.1.12** Add type hints to `data_loader._find_columns_for_file(...) -> Tuple[str, str, bool, Optional[str], List[str], Optional[str]]:`.

**2.1.13** Add type hints to `data_loader._parse_date_column(...) -> pd.Series:`.

**2.1.14** Add type hints to `data_loader._convert_value_columns(...) -> List[str]:`.

**2.1.15** Add type hints to `data_loader._process_single_file(...) -> Optional[Tuple[pd.DataFrame, List[str], Optional[str]]]:`.

**2.1.16** Add type hints to `data_loader.load_and_process_data(...) -> LoadResult:` using the defined `LoadResult` type alias.

**2.1.17** Add type hints to `metric_calculator._calculate_column_stats(...) -> Dict[str, Any]:`.

**2.1.18** Add type hints to `metric_calculator._process_dataframe_metrics(...) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:`.

**2.1.19** Add type hints to `metric_calculator.calculate_latest_metrics(...) -> pd.DataFrame:`.

**2.1.20** Add type hints to `security_processing.load_and_process_security_data(filename: str, data_folder_path: str) -> Tuple[pd.DataFrame, List[str]]:`.

**2.1.21** Add type hints to `security_processing.calculate_security_latest_metrics(df: pd.DataFrame, static_cols: List[str]) -> pd.DataFrame:`.

**2.1.22** Add type hints to `curve_processing._term_to_days(term_str: str) -> Optional[int]:`.

**2.1.23** Add type hints to `curve_processing.load_curve_data(data_folder_path: str) -> pd.DataFrame:`.

**2.1.24** Add type hints to `curve_processing.get_latest_curve_date(df: pd.DataFrame) -> Optional[pd.Timestamp]:`.

**2.1.25** Add type hints to `curve_processing.check_curve_inconsistencies(df: pd.DataFrame) -> Dict[str, Any]:`.

**2.1.26** Add type hints to `issue_processing.load_issues(data_folder_path: str) -> pd.DataFrame:`.

**2.1.27** Add type hints to `issue_processing.add_issue(...) -> str:`.

**2.1.28** Add type hints to `issue_processing.close_issue(...) -> bool:`.

**2.1.29** Add type hints to `data_validation.validate_data(df: pd.DataFrame, filename: str) -> Tuple[bool, List[str]]:`.

**2.1.30** Add type hints to functions in `views/**/*.py` and preprocessing scripts (`process_data.py`, `weight_processing.py`), focusing on helper functions first.

## 2.2 Eliminate Hardcoded Values/Logic

**2.2.1** In `config.py`, define constants for standard column names used frequently: `FUNDS_COL = 'Funds'`, `ISIN_COL = 'ISIN'`, `SEC_NAME_COL = 'Security Name'`, `DATE_COL = 'Date'`, `VALUE_COL = 'Value'`, etc.. [Complete]

**2.2.2** Replace hardcoded string literals like 'ISIN', 'Funds', 'Date', 'Value', 'Security Name' in `.py` files (e.g., `utils.py`, `data_loader.py`, `security_processing.py`, views) with the constants defined in `config.py`. [Complete]

**2.2.3** In `maxmin_processing.py`, replace the hardcoded `META_COLS = 6` with a dynamically determined index or a list of known metadata column names defined in `config.py`. [Complete]

**2.2.4** In `staleness_processing.py`, replace the hardcoded `META_COLS = 6` similar to step 2.2.3. [Complete]

**2.2.5** In `staleness_processing.py`, move `DEFAULT_PLACEHOLDER_VALUES = [100]` to `config.py` as `STALENESS_PLACEHOLDERS: List[Union[int, str]]`. Update `staleness_processing.py` and `direct_test.py` to use this config variable. [Complete]

**2.2.6** In `staleness_processing.py`, move `DEFAULT_STALENESS_THRESHOLD_DAYS = 5` to `config.py` as `STALENESS_THRESHOLD_DAYS: int`. Update `staleness_processing.py` and `test_staleness.py` to use this. [Complete]

**2.2.7** In `curve_processing.py`, move `CURVE_MONOTONICITY_DROP_THRESHOLD = -0.5`, `CURVE_ANOMALY_STD_MULTIPLIER = 3`, `CURVE_ANOMALY_ABS_THRESHOLD = 0.2` from `config.py` into the `check_curve_inconsistencies` function signature with defaults, or keep in config if external configuration is desired. Review if these should be configurable per-currency. [Complete]

**2.2.8** In `views/security_views.py`, replace hardcoded `PER_PAGE = 50` with a constant `SECURITIES_PER_PAGE` in `config.py`. [Complete]

**2.2.9** In `views/generic_comparison_views.py`, replace hardcoded `PER_PAGE_COMPARISON = 50` with a constant `COMPARISON_PER_PAGE` in `config.py`. [Complete]

**2.2.10** Review `utils._is_date_like`. Consider if the date patterns should be moved to `config.py` or if a more robust date parsing approach (e.g., trying multiple formats with `pd.to_datetime`) should be used universally, reducing reliance on regex patterns. Implement the improved parsing in `_is_date_like` or a new utility function. [Complete]

**2.2.11** In `process_data.py`, examine the ISIN suffixing logic (`f"{str(original_isin)}-{i+1}"`). Determine if this suffixing (`-1`, `-2`) is always desired or should be configurable. Refactor into a helper function, potentially taking a suffix pattern from config. [Complete]

**2.2.12** In `data_loader.py`, review the column finding logic (`_find_column` using regex patterns like `r'\b(Position\s*)?Date\b'`). Make these patterns configurable in `config.py` (e.g., `DATE_COLUMN_PATTERNS = [r'\bDate\b', r'\bPosition\s*Date\b']`). [Complete]

**2.2.13** Review `views/attribution_views.py` for hardcoded L1/L2 factor names/groupings. Consider moving these definitions to `config.py` if they might change. [Complete]

**2.2.14** In `views/generic_comparison_views.py` `calculate_generic_comparison_stats`, review the hardcoded list of statistic keys `expected_keys`. Ensure this list aligns with the actual calculated keys. [Complete]

**2.2.15** In `templates/watchlist_page.html`, the `min-width` and `width` for the 'Reason' column are hardcoded. Move these styling details purely to CSS or Tailwind classes if possible. [Complete]

**2.2.16** Review `playwright_screenshot_all.py`. Move example data (`EXAMPLE_METRIC`, `EXAMPLE_SECURITY_ID`, etc.) and selectors into a separate configuration section or file to avoid hardcoding within the script logic. [Complete]

**2.2.17** Review `direct_test.py`. Move test parameters (`SECURITY_ID`, `CSV_FILE`, `PLACEHOLDER_VALUE`, `CONSECUTIVE_THRESHOLD`) to command-line arguments or a config section. [Complete]

**2.2.18** Review `staleness_detection.py`. Ensure placeholder values and threshold come from config or arguments, not hardcoded defaults within the function logic. [Complete]

**2.2.19** Review `weight_processing.py`. The logic for detecting metadata columns relies on heuristics (`detect_metadata_columns`). Could this be made more explicit or configurable? Evaluate if the `min_numeric_cols` default of 3 is robust. [Complete]

**2.2.20** Review `views/security_details.py`. The grouping logic for static info relies on hardcoded lists of column names. Consider making these groupings configurable if the `reference.csv` schema changes frequently. [Complete]

## 2.3 Enhance Error Handling & Validation

**2.3.1** In `app.py` `run_cleanup`, replace `except Exception as e:` with more specific exceptions like `FileNotFoundError`, `SubprocessError`, `TimeoutExpired`.

**2.3.2** In `app.py` `create_app`, add specific `try...except` blocks around blueprint registration to catch potential `ImportError` or other issues during setup.

**2.3.3** In `curve_processing.py` `load_curve_data`, refine the final `except Exception as e:` to catch more specific `IOError`, `PermissionError`, etc., if possible.

**2.3.4** In `curve_processing.py` `check_curve_inconsistencies`, refine the final `except Exception as e:` to catch specific Pandas errors like `IndexError`, `KeyError`.

**2.3.5** In `data_loader.py` `_process_single_file`, refine the final `except Exception as e:` and the `except Exception as e:` around the `pd.read_csv` call. Catch `FileNotFoundError`, `pd.errors.ParserError`, `PermissionError`, `OSError`, `ValueError` explicitly.

**2.3.6** In `security_processing.py` `load_and_process_security_data`, refine the `except Exception as e:` blocks. Catch specific Pandas errors during reading and melting.

**2.3.7** In `security_processing.py` `calculate_security_latest_metrics`, refine the `except Exception as inner_e:` and `except Exception as e:` blocks.

**2.3.8** In `utils.py` `load_weights_and_held_status`, refine `except Exception as e:` to catch specific errors related to file I/O and Pandas operations.

**2.3.9** In `process_data.py` `process_csv_file`, refine `except Exception as e:` to handle specific file/parsing/permission errors.

**2.3.10** In `weight_processing.py` `process_weight_file`, refine `except Exception as e:` to handle specific file/parsing/permission errors.

**2.3.11** In `data_validation.py` `validate_data`, implement checks for `ts_*.csv` files: verify `Date` is datetime-parseable, `Code` exists, and value columns are numeric. [Complete]

**2.3.12** In `data_validation.py` `validate_data`, implement checks for `sec_*.csv` files: verify an ID column exists (e.g., `ISIN`), date-like columns are parseable, and value columns are numeric. [Complete]

**2.3.13** In `data_validation.py` `validate_data`, implement checks for `FundList.csv`: verify required columns exist (`Fund Code`, `Total Asset Value USD`, `Picked`). [Complete]

**2.3.14** In `data_validation.py` `validate_data`, implement checks for `w_*.csv` files: verify ID column exists, date columns are parseable, weight columns are numeric. [Complete]

**2.3.15** In `views/api_routes_call.py`, integrate calls to `data_validation.validate_data` after fetching data (`_fetch_real_tqs_data`) and before saving/merging (`_save_or_merge_data`). [Complete]

**2.3.16** Modify `_save_or_merge_data` in `views/api_routes_call.py` to handle the validation status. If validation fails, log the errors and potentially skip saving or save to a quarantined location. Update the `summary['status']` accordingly. [Complete]

**2.3.17** In `data_loader.py` `_process_single_file`, add more specific logging when dropping rows due to NaN values after type conversion or date parsing, indicating which column caused the drop. [Complete]

**2.3.18** In `curve_processing.py` `load_curve_data`, improve logging when dropping rows due to unparseable 'Date' or non-numeric 'Value', showing examples of dropped values if feasible. [Complete]

**2.3.19** In `security_processing.py` `load_and_process_security_data`, improve logging when dropping rows due to missing required values, specifying which values were missing. [Complete]

**2.3.20** In `views/api_core.py` `_fetch_real_tqs_data`, add more specific logging or exception handling if the `tqs` library (currently commented out) raises specific API-related exceptions. [Complete]

---

# PHASE 3: Refactoring Core Logic (Data Loading, Config)

## 3.1 Refactor Data Loading/Processing Logic

**3.1.1** Create a new file `data_utils.py`

**3.1.2** Define a function `read_csv_robustly(filepath: str, **kwargs) -> Optional[pd.DataFrame]` in `data_utils.py`. This function should handle `FileNotFoundError`, `pd.errors.EmptyDataError`, `pd.errors.ParserError`, `UnicodeDecodeError` with logging, and return `None` on error. It should accept standard `pd.read_csv` kwargs.

**3.1.3** Refactor `data_loader.load_simple_csv` to use `data_utils.read_csv_robustly`.

**3.1.4** Refactor `security_processing.load_and_process_security_data` (header read and full read) to use `data_utils.read_csv_robustly`.

**3.1.5** Refactor `curve_processing.load_curve_data` to use `data_utils.read_csv_robustly`.

**3.1.6** Refactor `issue_processing.load_issues` and `load_fund_list` to use `data_utils.read_csv_robustly`.

**3.1.7** Refactor `utils.load_exclusions` and `load_weights_and_held_status` to use `data_utils.read_csv_robustly`.

**3.1.8** Refactor `process_data.py` and `weight_processing.py` to use `data_utils.read_csv_robustly`.

**3.1.9** Define a function `parse_dates_robustly(series: pd.Series, formats: List[str] = None) -> pd.Series` in `data_utils.py`. It should try standard formats (YYYY-MM-DD, DD/MM/YYYY, ISO8601) and `pd.to_datetime` inference, log warnings on failures, and return the series with NaT for unparseable values.

**3.1.10** Refactor `data_loader._parse_date_column` to use `data_utils.parse_dates_robustly`.

**3.1.11** Refactor date parsing logic in `security_processing.load_and_process_security_data` to use `data_utils.parse_dates_robustly`.

**3.1.12** Refactor date parsing logic in `curve_processing.load_curve_data` to use `data_utils.parse_dates_robustly`.

**3.1.13** Define a function `identify_columns(columns: List[str], patterns: Dict[str, List[str]], required: List[str]) -> Dict[str, Optional[str]]` in `data_utils.py`. `patterns` maps a category (e.g., 'date', 'id') to regex patterns. It finds the first match for each category. Checks if `required` categories are found.

**3.1.14** Refactor `data_loader._find_column` and `_find_columns_for_file` to use `data_utils.identify_columns`. Load patterns from `config.py`.

**3.1.15** Refactor column identification in `security_processing.load_and_process_security_data` to use `data_utils.identify_columns`.

**3.1.16** Define a function `convert_to_numeric_robustly(series: pd.Series) -> pd.Series` in `data_utils.py` using `pd.to_numeric(errors='coerce')`.

**3.1.17** Refactor `data_loader._convert_value_columns` to use `data_utils.convert_to_numeric_robustly` on each specified column.

**3.1.18** Refactor numeric conversion in `security_processing.load_and_process_security_data` to use `data_utils.convert_to_numeric_robustly`.

**3.1.19** Define a function `melt_wide_data(df: pd.DataFrame, id_vars: List[str], date_like_check_func: Callable = utils._is_date_like) -> Optional[pd.DataFrame]` in `data_utils.py`. It should identify date columns using the check function, perform the melt, parse dates, and return the long DataFrame or None on error.

**3.1.20** Refactor melting logic in `security_processing.load_and_process_security_data` to use `data_utils.melt_wide_data`.

**3.1.21** Refactor melting logic in `utils.load_weights_and_held_status` (for wide format) to use `data_utils.melt_wide_data`.

**3.1.22** Review `data_loader._process_single_file`. Ensure it now primarily orchestrates calls to the new `data_utils` functions (read, identify columns, parse dates, convert numeric, melt if needed).

**3.1.23** Review `security_processing.load_and_process_security_data`. Ensure it uses the new `data_utils` functions appropriately.

**3.1.24** Create unit tests in `tests/utils/test_data_utils.py` for the new functions: `read_csv_robustly`, `parse_dates_robustly`, `identify_columns`, `convert_to_numeric_robustly`, `melt_wide_data`.

**3.1.25** Rerun all tests (`pytest`) to ensure refactoring hasn't broken existing functionality.

## 3.2 Improve Configuration Management

**3.2.1** Create a new file named `comparison_config.yaml` (or `.json`) in the project root or a dedicated `config/` directory.

**3.2.2** Move the structure defined in `COMPARISON_CONFIG` in `config.py` into `comparison_config.yaml`.

```yaml
# Example comparison_config.yaml
spread:
  display_name: 'Spread'
  file1: 'sec_spread.csv'
  file2: 'sec_spreadSP.csv'
  value_label: 'Spread'
duration:
  display_name: 'Duration'
  # ... etc
```

**3.2.3** In `config.py` or `utils.py`, add a function `load_yaml_config(filepath)` using the `PyYAML` library (add `PyYAML` to `requirements.txt`).

**3.2.4** In `config.py`, remove the hardcoded `COMPARISON_CONFIG` dictionary. Instead, load it using `load_yaml_config('comparison_config.yaml')` when the module is imported. Store the result in the `COMPARISON_CONFIG` variable.

**3.2.5** Update `views/generic_comparison_views.py` to ensure it still accesses the loaded `COMPARISON_CONFIG` correctly.

**3.2.6** Create a new file named `maxmin_thresholds.yaml` (or `.json`).

**3.2.7** Move the structure defined in `MAXMIN_THRESHOLDS` in `config.py` into `maxmin_thresholds.yaml`.

```yaml
# Example maxmin_thresholds.yaml
sec_Spread.csv:
  min: -50
  max: 1000
  display_name: 'Spread'
  group: 'Spreads'
# ... etc
```

**3.2.8** In `config.py`, remove the hardcoded `MAXMIN_THRESHOLDS` dictionary. Load it using `load_yaml_config('maxmin_thresholds.yaml')` and store it in the `MAXMIN_THRESHOLDS` variable.

**3.2.9** Update `views/maxmin_views.py` to ensure it accesses the loaded `MAXMIN_THRESHOLDS` correctly.

**3.2.10** Update `maxmin_processing.py` if it directly imports `MAXMIN_THRESHOLDS` from `config.py`. It should now receive the configuration as an argument. Modify `views/maxmin_views.py` to pass the loaded config to `get_breach_summary`.

**3.2.11** Create `tests/config/test_config_loading.py`.

**3.2.12** Add tests in `test_config_loading.py` to mock the YAML files and verify that `config.COMPARISON_CONFIG` and `config.MAXMIN_THRESHOLDS` are loaded correctly. Mock `load_yaml_config`.

**3.2.13** Create `config/date_patterns.yaml` (or similar). Move regex patterns used in `utils._is_date_like` and `data_loader._find_column` to this file.

**3.2.14** Modify `utils.py` and `data_loader.py` to load these patterns from the YAML file instead of having them hardcoded.

**3.2.15** Add `PyYAML` to `requirements.txt`.

---

# PHASE 4: Testing & Refactoring Larger Components

## 4.1 Improve Test Suite Coverage

**4.1.1** Run `pytest --cov=. --cov-report=html` to generate a coverage report (`htmlcov/index.html`).

**4.1.2** Open the coverage report and identify modules/files with low coverage (e.g., `views/*.py`, complex functions in processing modules).

**4.1.3** (Views) Add tests in `tests/views/` for untested routes or untested logic within routes (e.g., different filter combinations, error paths, edge cases like empty data after filtering).

**4.1.4** (Views - generic_comparison_views) In `tests/views/test_generic_comparison_views.py`, add tests specifically for pagination logic (requesting different pages, checking content), sorting logic (requesting different `sort_by`/`sort_order`, checking output order), and filter combinations.

**4.1.5** (Views - security_views) In `tests/views/test_security_views.py`, add more tests for pagination, sorting, and combinations of filters (search, static columns, exclude min zero).

**4.1.6** (Views - metric_views) In `tests/views/test_metric_views.py`, add tests for the `/inspect` and `/inspect/results` routes, mocking `_calculate_contributions` and verifying input handling and template context.

**4.1.7** (Processing) Add tests in `tests/processing/` for edge cases in calculation functions (e.g., `metric_calculator` with all NaNs, single data point; `security_processing` with varied date formats).

**4.1.8** (Processing - _calculate_contributions) Add tests specifically for `views.metric_views._calculate_contributions`, mocking the data loading (`load_simple_csv`, `_melt_data`) and testing the baseline calculation, averaging, difference calculation, and ranking logic with various inputs (missing baseline, no data in period, all zeros).

**4.1.9** (Error Handling) Add tests that specifically trigger error conditions (e.g., mock file loading to raise `PermissionError`, mock calculations to raise `ValueError`) and assert that the application handles them gracefully (e.g., returns correct HTTP status, flashes appropriate message, renders error template).

**4.1.10** (Validation) Add tests in `tests/processing/test_data_validation.py` for the `validate_data` function, providing mock DataFrames representing valid and invalid schemas for different file types (`ts_`, `sec_`, `w_`, etc.) and asserting the correct validation result and error messages.

**4.1.11** (Utils) Add tests in `tests/utils/test_utils.py` for `_is_date_like` covering various valid/invalid formats identified during analysis.

**4.1.12** (Utils) Add tests in `tests/utils/test_utils.py` for `parse_fund_list` covering `[A,B]`, `[A]`, `[]`, `A,B`, `[ A , B ]`, invalid formats.

**4.1.13** (Utils) Add tests in `tests/utils/test_utils.py` for `replace_nan_with_none` covering nested dicts, lists, `np.nan`, `pd.NA`, standard floats/ints.

**4.1.14** (Utils) Add tests in `tests/utils/test_utils.py` for `load_fund_groups` covering file not found, empty file, file with various group structures.

**4.1.15** Aim for a higher overall coverage percentage (e.g., >80-85%), focusing on critical logic paths.

## 4.2 Refactor Large Functions/Modules

**4.2.1** (data_loader._process_single_file) Identify distinct logical steps within this function: reading header, finding columns, reading data, filtering (S&P valid), aggregating (if not filtering), renaming, date parsing, indexing, type conversion.

**4.2.2** (data_loader._process_single_file) Ensure most steps now call the helper functions created in Area 1 (e.g., `read_csv_robustly`, `identify_columns`, `parse_dates_robustly`, `convert_to_numeric_robustly`).

**4.2.3** (data_loader._process_single_file) Extract the S&P valid filtering logic (`if filter_sp_valid...`) into a separate helper function `_filter_by_scope(df, scope_column_name) -> pd.DataFrame`.

**4.2.4** (data_loader._process_single_file) Extract the aggregation logic (`if not filter_sp_valid...`) into a separate helper function `_aggregate_by_date_code(df, date_col, code_col, value_cols) -> pd.DataFrame`.

**4.2.5** (metric_calculator.calculate_latest_metrics) Identify distinct steps: preparing combined data, calculating primary base metrics, calculating secondary base metrics, calculating primary relative metrics, calculating secondary relative metrics, combining, sorting.

**4.2.6** (metric_calculator.calculate_latest_metrics) Use the existing helper `_process_dataframe_metrics` for base metrics calculation (primary and secondary).

**4.2.7** (metric_calculator.calculate_latest_metrics) Extract the logic for calculating primary relative metrics into a new helper function `_calculate_relative_metrics(df, fund_codes, fund_col, bench_col, latest_date, prefix) -> pd.DataFrame`.

**4.2.8** (metric_calculator.calculate_latest_metrics) Call `_calculate_relative_metrics` for both primary and secondary data.

**4.2.9** (metric_calculator.calculate_latest_metrics) Refactor the final merging and sorting logic for clarity.

**4.2.10** (views.generic_comparison_views.summary) Identify distinct steps: validate config, get request params, load data, calculate stats, load/merge held status, apply fund group filter, generate filter options, apply static filters, apply sorting, paginate, prepare context.

**4.2.11** (views.generic_comparison_views.summary) Move data loading (`load_generic_comparison_data`) and stats calculation (`calculate_generic_comparison_stats`) calls to the top.

**4.2.12** (views.generic_comparison_views.summary) Move held status loading/merging logic (`load_weights_and_held_status`) immediately after stats calculation.

**4.2.13** (views.generic_comparison_views.summary) Encapsulate the filtering logic (fund group, holding status, static filters) into a helper function `_apply_summary_filters(df, fund_group, show_sold, active_filters) -> pd.DataFrame`.

**4.2.14** (views.generic_comparison_views.summary) Encapsulate the sorting logic into a helper function `_apply_summary_sorting(df, sort_by, sort_order, id_col) -> pd.DataFrame`.

**4.2.15** (views.generic_comparison_views.summary) Encapsulate pagination logic into a helper function `_paginate_summary_data(df, page, per_page) -> Tuple[pd.DataFrame, Dict]`.

**4.2.16** (views.generic_comparison_views.details) Identify distinct steps: decode ID, validate config, load data, filter security, calculate stats, prepare chart data, get holdings data, render. Keep this view function focused, relying on helpers from `comparison_helpers.py`.

**4.2.17** (views.security_views.securities_page) Similar to comparison summary, identify steps: get params, load data, calc metrics, load/apply exclusions, apply filters (fund group, search, static, min=0), apply sorting, paginate, prepare context.

**4.2.18** (views.security_views.securities_page) Refactor filtering logic into a helper function `_apply_security_filters(...)`.

**4.2.19** (views.security_views.securities_page) Refactor sorting logic into a helper function `_apply_security_sorting(...)`.

**4.2.20** (views.security_views.securities_page) Refactor pagination logic into a helper function `_paginate_security_data(...)`.

---

# PHASE 5: Consolidate Preprocessing & Final Cleanup

## 5.1 Refactor/Consolidate `process_data.py` & `weight_processing.py`

**5.1.1** Create a new file `preprocessing.py`.

**5.1.2** Define constants in `preprocessing.py` or `config.py` for filename prefixes (`PRE_PREFIX = 'pre_'`, `SEC_PREFIX = 'sec_'`, `WEIGHT_PREFIX = 'w_'`, `PRE_WEIGHT_PREFIX = 'pre_w_'`).

**5.1.3** Move the `read_and_sort_dates` function from `process_data.py` to `preprocessing.py` (or `data_utils.py` if more appropriate). Update imports in `process_data.py` and `weight_processing.py`.

**5.1.4** Move the `detect_metadata_columns` function from `weight_processing.py` to `preprocessing.py` (or `data_utils.py`). Update imports.

**5.1.5** Analyze the core logic of `process_data.replace_headers_with_dates` and the header replacement logic within `weight_processing.process_weight_file`. Create a single, unified function `replace_headers_with_dates(df: pd.DataFrame, date_columns: List[str], metadata_cols: List[str]) -> pd.DataFrame` in `preprocessing.py`. This function should handle identifying data columns (those not in `metadata_cols`) and replacing them with the provided `date_columns`, managing count mismatches with logging.

**5.1.6** Analyze the core logic of `process_data.aggregate_data`. Move this function to `preprocessing.py`.

**5.1.7** Create a main function `process_input_file(input_path: str, output_path: str, dates_path: str, config: Dict)` in `preprocessing.py`. This function will:
  * Determine file type based on `input_path` filename (e.g., 'ts', 'pre', 'w', 'pre_w').
  * Read the file using `data_utils.read_csv_robustly`.
  * Load dates using `read_and_sort_dates`.
  * If it's a `pre_` file (not `pre_w_`): Call `replace_headers_with_dates` and `aggregate_data`, then save to `output_path` (prefixed with `sec_`).
  * If it's a `pre_w_` file: Identify metadata columns (dynamically for `w_secs`), call `replace_headers_with_dates`, then save to `output_path` (prefixed with `w_`).
  * Handle errors gracefully.

**5.1.8** Create a new script `run_preprocessing.py` that:
  * Gets the data folder path.
  * Finds all `pre_*.csv` files.
  * Calls `preprocessing.process_input_file` for each file, determining the correct output path and passing necessary config/dates path.

**5.1.9** Refactor the Flask endpoint `/run-cleanup` in `app.py` to call `run_preprocessing.main()` (or a similar entry point) instead of directly running `process_data.py`.

**5.1.10** Delete the old `process_data.py` and `weight_processing.py` files.

**5.1.11** Update any import statements that previously pointed to the deleted files (e.g., in tests).

**5.1.12** Create `tests/processing/test_preprocessing.py`.

**5.1.13** Add unit tests for the new `preprocessing.py` functions (`replace_headers_with_dates`, `aggregate_data`, `process_input_file`). Mock file I/O and test different file types and edge cases.

**5.1.14** Add integration tests in `tests/integration/` that run `run_preprocessing.py` on a set of dummy input files (`pre_*.csv`) in a temporary directory and verify the output files (`sec_*.csv`, `w_*.csv`) are created correctly.

**5.1.15** Rerun all tests (`pytest`).

## 5.2 Final Review & Cleanup

**5.2.1** Review all files modified during the refactoring process. Look for any remaining complex functions or potential code duplication that might have been missed.

**5.2.2** Check for any unused imports across all Python files and remove them.

**5.2.3** Ensure logging messages are informative and consistent. Remove excessive `print` statements used for debugging. Check `exc_info=True` is used appropriately in error logs.

**5.2.4** Verify that all configuration is now loaded from `config.py` or external files, and no sensitive or environment-specific values are hardcoded.

**5.2.5** Ensure all helper functions in `utils.py`, `data_utils.py`, `preprocessing.py`, etc., have clear docstrings and type hints.

**5.2.6** Rerun code style checks (`black .` and `flake8 .`) and fix any reported issues.

**5.2.7** Rerun the full test suite (`pytest --cov=.`) and ensure all tests pass and coverage remains high.

**5.2.8** Review the `Docs/` folder, especially `README.md` and `Features.md`, and update them to reflect the refactored code structure, new configuration methods, and any changes in functionality or file processing.

**5.2.9** Manually run the application (`flask run`) and test key features interactively (dashboard, metric pages, comparison pages, security details, exclusions, issues, get data page) to catch any issues missed by automated tests.

**5.2.10** Commit the final, refactored codebase.

# Phase 6: Check up with Gemini
**6.1** has 2.1 been fully completed
**6.2** has 2.2.1 been fully completed
---