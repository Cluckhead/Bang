### Test Coverage Improvement Plan

**Overall Goal:** Increase the test coverage significantly from the current 34%. Focus on core application logic, views, and utility functions.

**Instructions for LLM Agent:**

- Use `pytest` for writing tests.
- Use the `pytest-mock` library (`mocker` fixture) to mock dependencies like file I/O (`open`, `pd.read_csv`, `os.path.exists`), external APIs (if any), database interactions (if any), and functions from other modules.
- Place new test files in the corresponding `tests/` subdirectory (e.g., tests for `views/watchlist_views.py` go in `tests/views/test_watchlist_views.py`).
- Ensure tests cover various scenarios: success paths, edge cases (e.g., empty data, invalid inputs), and error handling (e.g., file not found, exceptions).
- Aim to cover all functions and branches within the specified files.
    
**Phase 1: Critical Views & Logic (0-10% Coverage)**

1. **Task:** Write unit tests for `views/watchlist_views.py`.
    
    - **Target File:** `views/watchlist_views.py`
        
    - **Test File:** `tests/views/test_watchlist_views.py` (Create if not exists)
        
    - **Functions to Test:** `load_watchlist`, `save_watchlist`, `load_users`, `load_available_securities`, `add_to_watchlist`, `clear_watchlist_entry`, `update_last_checked`, `manage_watchlist` (GET/POST), `clear_watchlist` (POST), `check_watchlist_entry` (GET).
        
    - **Mocking:** Mock file operations (`pd.read_csv`, `os.path.exists`, `df.to_csv`), `load_available_securities`, `load_users`. Test logic for adding/clearing entries, checking for existing active entries, loading/saving CSV data. Test the view routes using the Flask test client, mocking helper functions.
        - **Testing Hints:**
            - **Application Context:** For testing helper functions (like `load_watchlist`) that use `current_app` (e.g., for `current_app.logger`, `current_app.config`), ensure they run within an application context using `with test_app.app_context():`. Inject the `test_app` fixture into the test function signature.
            - **`url_for` Context:** `url_for()` needs an application context. When generating URLs for redirects or links *within your view function*, ensure `app.config['SERVER_NAME']` is set in the test app config (e.g., in `conftest.py`).
            - **Test Client Usage:** Prefer using **literal paths** (e.g., `client.get("/your-route")`) over generating URLs with `url_for()` when making requests with the Flask test client (`client.get`, `client.post`). This avoids context and `SERVER_NAME` complexities.
            - **Fixture Usage:** In view tests, use only the `client` fixture in the test function signature (e.g., `def test_my_view(client, mocker):`). If you need the app instance, access it via `client.application`. Avoid using both `test_app` and `client` fixtures directly in the test signature.
            - **Nested `conftest.py`:** Be aware of nested `conftest.py` files (e.g., `tests/views/conftest.py`). Fixtures defined in these files **override** fixtures from parent directories for tests within that subdirectory. Ensure the *local* `conftest.py` fixture (e.g., `app` or `test_app`) configures the app correctly for the specific tests.
            - **Blueprint Dependencies:** The test app fixture (whether root or local) **must** register the blueprint being tested *and* **any other blueprints whose routes are used via `url_for()` within the view's template or any base template it extends** (e.g., `base.html`). Failure to register dependencies will cause `BuildError` during template rendering. Check `base.html` and included templates for `url_for` calls.
            - **Response Assertions:** When asserting content in `response.data`, check against the *actual* rendered HTML source, not just assumed text (e.g., `assert b"Actual Page Title" in response.data`).
            - **Avoid Global Mocks:** Avoid patching Flask built-ins like `flask.redirect` or `flask.url_for` globally, as it can interfere with the test client, especially `follow_redirects`. Test redirects by checking `response.status_code` or `response.request.path` (if `follow_redirects=True`).
            - **Flash Messages:** Test flash messages using the client's session: `with client.session_transaction() as sess: sess['_flashes'] = []` before the request, and check `sess.get('_flashes', [])` after.
        
2. **Task:** Write unit tests for `views/maxmin_views.py` and `maxmin_processing.py`.
    
    - **Target Files:** `views/maxmin_views.py`, `maxmin_processing.py`
        
    - **Test Files:** `tests/views/test_maxmin_views.py`, `tests/processing/test_maxmin_processing.py` (Create if not exists)
        
    - **Functions to Test:** `maxmin_processing.find_value_breaches`, `maxmin_processing.get_breach_summary`, `maxmin_processing.get_breach_details`, `views.maxmin_views.dashboard` (GET), `views.maxmin_views.details` (GET).
        
    - **Mocking:** Mock `pd.read_csv`, `os.path.exists`, `config.MAXMIN_THRESHOLDS`. Test breach detection logic with various thresholds and data values (including NaNs). Test view routes with different query parameters (overrides, group_name) and mock the processing functions.
        
3. **Task:** Write unit tests for `views/attribution_views.py`.
    
    - **Target File:** `views/attribution_views.py`
        
    - **Test File:** `tests/views/test_attribution_views.py` (Expand existing)
        
    - **Functions to Test:** `get_available_funds`, `attribution_summary` (GET), `attribution_charts` (GET), `attribution_radar` (GET), `attribution_security_page` (GET).
        
    - **Mocking:** Mock file operations (`pd.read_csv`, `os.path.exists`), `w_secs.csv` loading, `config.ATTRIBUTION_L1_GROUPS`, `config.ATTRIBUTION_L2_GROUPS`. Test data loading for specific funds, filtering logic (date, characteristic, level), aggregation logic for different levels (L0, L1, L2), and data preparation for charts/tables. Use the Flask test client.
        
4. **Task:** Write unit tests for `views/metric_views.py`.
    
    - **Target File:** `views/metric_views.py`
        
    - **Test File:** `tests/views/test_metric_views.py` (Expand existing)
        
    - **Functions to Test:** `metric_page` (GET), `_calculate_contributions`, `inspect_metric_contribution` (POST), `inspect_results_page` (GET).
        
    - **Mocking:** Mock `load_and_process_data`, `calculate_latest_metrics`, `load_simple_csv`, `_melt_data`, `reference.csv` loading. Test `metric_page` with/without secondary data, with/without fund group filter. Test `_calculate_contributions` logic thoroughly (baseline, average, diff, ranking). Test API endpoint and results page rendering. Use the Flask test client.
        
5. **Task:** Write unit tests for `views/api_core.py`.
    
    - **Target File:** `views/api_core.py`
        
    - **Test File:** `tests/views/test_api_core.py` (Create if not exists)
        
    - **Functions to Test:** `_simulate_and_print_tqs_call`, `_fetch_real_tqs_data` (mock external API), `_find_key_columns`, `get_data_file_statuses`.
        
    - **Mocking:** Mock `tqs` library (if `USE_REAL_TQS_API` is True), `pd.read_csv`, `os.path.exists`, `os.path.getmtime`, `datetime.datetime`. Test column finding logic, file status retrieval, API simulation output, and error handling in real API fetch.
        
6. **Task:** Write unit tests for `views/security_views.py`.
    
    - **Target File:** `views/security_views.py`
        
    - **Test File:** `tests/views/test_security_views.py` (Expand existing)
        
    - **Functions to Test:** `get_active_exclusions`, `securities_page` (GET), `security_details` (GET).
        
    - **Mocking:** Mock `load_and_process_security_data`, `calculate_security_latest_metrics`, `load_exclusions`, `reference.csv` loading, `issue_processing` functions, `get_holdings_for_security`. Test filtering (search, static, min=0, fund group), sorting, pagination logic in `securities_page`. Test data loading and chart data preparation in `security_details`. Use the Flask test client.
        
7. **Task:** Write unit tests for `views/fund_views.py`.
    
    - **Target File:** `views/fund_views.py`
        
    - **Test File:** `tests/views/test_fund_views.py` (Expand existing)
        
    - **Functions to Test:** `fund_duration_details` (GET), `fund_detail` (GET).
        
    - **Mocking:** Mock `load_and_process_security_data`, `load_and_process_data`, `w_secs.csv` loading, `read_and_sort_dates`, `glob.glob`. Test duration details calculation and filtering. Test `fund_detail` aggregation logic across multiple metric files, including SP data handling and chart data preparation. Use the Flask test client.
        
8. **Task:** Write unit tests for `views/curve_views.py`.
    
    - **Target File:** `views/curve_views.py`
        
    - **Test File:** `tests/views/test_curve_views.py` (Expand existing)
        
    - **Functions to Test:** `curve_summary` (GET), `curve_details` (GET).
        
    - **Mocking:** Mock `load_curve_data`, `check_curve_inconsistencies`, `get_latest_curve_date`. Test summary generation. Test details page with different dates and `prev_days` parameters, including chart data prep and table calculation. Use the Flask test client.
        
9. **Task:** Write unit tests for `data_validation.py`.
    
    - **Target File:** `data_validation.py`
        
    - **Test File:** `tests/processing/test_data_validation.py` (Create if not exists)
        
    - **Functions to Test:** `validate_data`, `_is_date_like`.
        
    - **Mocking:** None needed for direct function tests. Provide various mock DataFrames (valid and invalid) for different file types (`ts_`, `sec_`, `w_`, `FundList`, etc.) and assert correct validation results and error messages. Test `_is_date_like` with various date/non-date strings.
        

**Phase 2: Important Views & Logic (10-30% Coverage)**

10. **Task:** Write unit tests for `views/exclusion_views.py`.
    
    - **Target File:** `views/exclusion_views.py`
        
    - **Test File:** `tests/views/test_exclusion_views.py` (Expand existing)
        
    - **Functions to Test:** `load_exclusions`, `load_available_securities`, `load_users`, `add_exclusion`, `remove_exclusion`, `manage_exclusions` (GET/POST), `remove_exclusion_route` (POST).
        
    - **Mocking:** Mock file operations (`pd.read_csv`, `os.path.exists`, `open`), `reference.csv` loading, `users.csv` loading. Test adding/removing logic, loading logic. Test view routes using Flask test client, mocking helpers.
        
11. **Task:** Write unit tests for `views/issue_views.py`.
    
    - **Target File:** `views/issue_views.py`
        
    - **Test File:** `tests/views/test_issue_views.py` (Expand existing)
        
    - **Functions to Test:** `load_users`, `manage_issues` (GET/POST), `close_issue_route` (POST).
        
    - **Mocking:** Mock `issue_processing` functions (`load_issues`, `add_issue`, `close_issue`, `load_fund_list`), `users.csv` loading. Test view routes for displaying, adding, and closing issues using Flask test client.
        
12. **Task:** Write unit tests for `views/weight_views.py`.
    
    - **Target File:** `views/weight_views.py`
        
    - **Test File:** `tests/views/test_weight_views.py` (Expand existing)
        
    - **Functions to Test:** `_parse_percentage`, `load_and_process_weight_data`, `weight_check` (GET).
        
    - **Mocking:** Mock `pd.read_csv`, `os.path.exists`. Test percentage parsing. Test loading/processing logic for different weight files. Test view route using Flask test client.
        
13. **Task:** Write unit tests for `views/staleness_views.py`.
    
    - **Target File:** `views/staleness_views.py`
        
    - **Test File:** `tests/views/test_staleness_views.py` (Expand existing)
        
    - **Functions to Test:** `get_display_name_for_staleness_file`, `dashboard` (GET), `details` (GET).
        
    - **Mocking:** Mock `staleness_processing` functions (`get_staleness_summary`, `get_stale_securities_details`), `load_exclusions`, `config` variables. Test display name logic. Test view routes with different thresholds and mock processing functions. Use Flask test client.
        
14. **Task:** Write unit tests for `views/generic_comparison_views.py`.
    
    - **Target File:** `views/generic_comparison_views.py`, `views/comparison_helpers.py`
        
    - **Test File:** `tests/views/test_generic_comparison_views.py` (Expand existing)
        
    - **Functions to Test:** `comparison_helpers.load_generic_comparison_data`, `comparison_helpers.calculate_generic_comparison_stats`, `comparison_helpers.get_holdings_for_security`, `views.generic_comparison_views.summary` (GET), `views.generic_comparison_views.details` (GET).
        
    - **Mocking:** Mock `load_and_process_security_data`, `load_weights_and_held_status`, `w_secs.csv` loading. Test data loading/merging, stats calculation (correlations, diffs), holdings lookup. Test view routes with different comparison types, filters, sorting, pagination. Use Flask test client.
        

**Phase 3: Core Logic & Utilities (30-70% Coverage)**

15. **Task:** Write unit tests for `process_data.py`.
    
    - **Target File:** `process_data.py`
        
    - **Test File:** `tests/processing/test_process_data.py` (Expand existing)
        
    - **Functions to Test:** `read_and_sort_dates`, `replace_headers_with_dates`, `aggregate_data`, `process_csv_file`, `main`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `df.to_csv`, `os.path.exists`, `os.listdir`), `weight_processing.process_weight_file`. Test date reading/sorting, header replacement logic (patterns A & B), aggregation logic (fund merging, ISIN suffixing), main script execution flow.
        
16. **Task:** Write unit tests for `utils.py`.
    
    - **Target File:** `utils.py`
        
    - **Test File:** `tests/utils/test_utils.py` (Expand existing)
        
    - **Functions to Test:** `load_yaml_config`, `_is_date_like`, `parse_fund_list`, `load_exclusions`, `load_weights_and_held_status`, `replace_nan_with_none`, `load_fund_groups`.
        
    - **Mocking:** Mock file I/O (`open`, `yaml.safe_load`, `pd.read_csv`, `os.path.exists`). Test YAML loading, date regex patterns, fund string parsing, exclusion/weight loading logic, NaN replacement, fund group loading.
        
17. **Task:** Write unit tests for `curve_processing.py`.
    
    - **Target File:** `curve_processing.py`
        
    - **Test File:** `tests/processing/test_curve_processing.py` (Expand existing)
        
    - **Functions to Test:** `_term_to_days`, `load_curve_data`, `get_latest_curve_date`, `check_curve_inconsistencies`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `os.path.exists`). Test term conversion, data loading/parsing, latest date finding, inconsistency checks (monotonicity, anomaly detection).
        
18. **Task:** Write unit tests for `metric_calculator.py`.
    
    - **Target File:** `metric_calculator.py`
        
    - **Test File:** `tests/processing/test_metric_calculator.py` (Expand existing)
        
    - **Functions to Test:** `_calculate_column_stats`, `_process_dataframe_metrics`, `calculate_latest_metrics`, `load_metrics_from_csv`.
        
    - **Mocking:** None needed for calculation functions if testing with direct DataFrame inputs. Mock `pd.read_csv` for `load_metrics_from_csv`. Test stat calculations (mean, max, min, change, Z-score), handling of NaNs, zero std dev, processing primary/secondary data, relative metrics, merging, and sorting logic.
        
19. **Task:** Write unit tests for `weight_processing.py`.
    
    - **Target File:** `weight_processing.py`
        
    - **Test File:** `tests/processing/test_weight_processing.py` (Expand existing)
        
    - **Functions to Test:** `clean_date_format`, `detect_metadata_columns`, `process_weight_file`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `df.to_csv`, `os.path.exists`). Test date cleaning, metadata detection (config vs dynamic), header replacement logic for different file types (`w_Funds`, `w_Bench`, `w_secs`), handling of date/column count mismatches.
        
20. **Task:** Write unit tests for `data_loader.py`.
    
    - **Target File:** `data_loader.py`
        
    - **Test File:** `tests/processing/test_data_loader.py` (Expand existing)
        
    - **Functions to Test:** `load_simple_csv`, `_find_column`, `_create_empty_dataframe`, `_find_columns_for_file`, `_parse_date_column`, `_convert_value_columns`, `_process_single_file`, `load_and_process_data`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `os.path.exists`), `data_utils` functions (or test them directly via `data_utils_test.py`). Test column finding logic, date/numeric parsing, S&P valid filtering, aggregation logic, processing primary/secondary files.
        
21. **Task:** Write unit tests for `security_processing.py`.
    
    - **Target File:** `security_processing.py`
        
    - **Test File:** `tests/processing/test_security_processing.py` (Expand existing)
        
    - **Functions to Test:** `find_all_date_columns`, `load_and_process_security_data`, `calculate_security_latest_metrics`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `os.path.exists`), `data_utils` functions. Test date column finding, wide-to-long melting, static column identification, metric calculations (latest, change, Z-score, mean, max, min).
        
22. **Task:** Write unit tests for `staleness_processing.py`.
    
    - **Target File:** `staleness_processing.py`
        
    - **Test File:** `tests/processing/test_staleness_processing.py` (Expand existing)
        
    - **Functions to Test:** `get_staleness_summary`, `get_stale_securities_details`.
        
    - **Mocking:** Mock file I/O (`pd.read_csv`, `os.path.exists`, `os.listdir`), `load_exclusions`. Test summary generation and details retrieval logic, including threshold application and exclusion filtering.
        
23. **Task:** Write unit tests for `data_utils.py`.
    
    - **Target File:** `data_utils.py`
        
    - **Test File:** `tests/utils/test_data_utils.py` (Create if not exists)
        
    - **Functions to Test:** `read_csv_robustly`, `parse_dates_robustly`, `identify_columns`, `convert_to_numeric_robustly`, `melt_wide_data`.
        
    - **Mocking:** Mock `pd.read_csv` for `read_csv_robustly`. Test robust file reading, date parsing with various formats, column identification with patterns, numeric conversion, and wide-to-long melting logic.
        

**Phase 4: App Setup & Remaining Views**

24. **Task:** Write unit tests for `app.py`.
    
    - **Target File:** `app.py`
        
    - **Test File:** `tests/test_app.py` (Create if not exists)
        
    - **Functions to Test:** `create_app`, `run_cleanup` (POST endpoint).
        
    - **Mocking:** Mock `config` loading, `os.makedirs`, logging handlers, blueprint imports/registration, `subprocess.run`. Test app factory creation with different configurations, logging setup, blueprint registration success/failure. Test the `/run-cleanup` endpoint using Flask test client, mocking `subprocess.run` for success and failure cases.
        
25. **Task:** Write unit tests for `views/main_views.py`.
    
    - **Target File:** `views/main_views.py`
        
    - **Test File:** `tests/views/test_main_views.py` (Expand existing)
        
    - **Functions to Test:** `index` (GET).
        
    - **Mocking:** Mock `os.listdir`, `load_and_process_data`, `calculate_latest_metrics`. Test dashboard data aggregation logic, handling of missing files or calculation errors. Use Flask test client.
        

**Phase 5: Review & Refine**

26. **Task:** Run `pytest --cov=. --cov-report=html` again.
    
27. **Task:** Analyze the new coverage report. Identify any remaining critical gaps, especially in error handling or complex conditional logic.
    
28. **Task:** Add specific tests for any missed branches or edge cases identified in the review.

**General Testing Guidelines (Apply to All Phases):**

- **Check Local `conftest.py`:** Before writing tests in a subdirectory (e.g., `tests/processing`, `tests/views`), check if a local `conftest.py` exists (e.g., `tests/views/conftest.py`). Fixtures defined here **override** those from parent directories (like `tests/conftest.py`) for tests within that subdirectory. Ensure the local fixture (e.g., `app` or `test_app`) provides the **complete necessary setup**, especially registering **all** required blueprints (see next point).
- **Register All Blueprint Dependencies:** When setting up the app fixture for view tests (whether root or local `conftest.py`), explicitly register **all** blueprints whose routes might be called via `url_for()`. This includes the blueprint being tested *and* any blueprints referenced directly or indirectly within the view's template or any base template it extends (e.g., check `base.html` for `url_for` calls in navigation). Failure to register dependencies is a common cause of `BuildError` during template rendering or 404s for linked assets.
- **Prefer Literal Paths:** Use `client.get("/actual/path")` or `client.post("/actual/path")` for making requests in tests instead of generating URLs with `url_for()` for the request itself. This avoids potential context issues and `url_for` resolution quirks (like unexpected prefix duplication) within the test environment. Use `url_for` mainly for verifying the *expected* `response.location` after a redirect, but double-check the expected path carefully.
- **Flash Message Testing:** To test flash messages set before a redirect, make the initial request with `follow_redirects=False` and then check the session: `with client.session_transaction() as sess: flashes = sess.get('_flashes', [])`. **Be aware:** This can sometimes be unreliable with the test client; the flash message might not appear in the session as expected. If encountering issues, prioritize asserting the redirect status code (302), the correct `response.location`, and the functional outcome of the request, potentially commenting out the direct flash assertion if necessary. Remember to clear the session (`sess.clear()`) before tests involving flash messages for better isolation.
- **Verify Assertion Text:** Double-check the exact text, capitalization, and HTML structure when asserting content in `response.data`. Match against the *actual* rendered source.
- **Use `client` Fixture Correctly:** Rely primarily on the `client` fixture for view tests and access the app instance via `client.application`. Avoid injecting both `app` and `client` into the same test function signature.
- **Test View Logic Paths:** Ensure tests cover different execution paths within view functions, especially those conditional on the return values of helper functions (e.g., testing both success and failure cases for `add_to_watchlist` or `update_last_checked`).