# Tests Documentation

## tests/utils/test_utils.py

### get_data_folder_path
- **test_get_data_folder_path_config_set**: Verifies that when `config.DATA_FOLDER` is set to a valid absolute path, the function returns that path.
- **test_get_data_folder_path_config_missing**: Simulates `ImportError` for `config` and checks that the function falls back to the default relative path resolved from the current working directory.
- **test_get_data_folder_path_relative_path**: Ensures that when `config.DATA_FOLDER` is a relative path, it is resolved relative to the current working directory.
- **test_get_data_folder_path_absolute_path**: Ensures that when `config.DATA_FOLDER` is an absolute path, it is used directly.
- **test_get_data_folder_path_path_not_exist**: Checks that if the resolved path does not exist, the function still returns the resolved path and logs a warning.

All tests use `pytest-mock` and `tmp_path` for safe mocking and filesystem isolation.

## tests/config/test_config.py

### config.py structure
- **test_color_palette_is_list**: Verifies that COLOR_PALETTE is a list of strings.
- **test_data_folder_is_string**: Checks that DATA_FOLDER is a non-empty string.
- **test_id_column_is_string**: Ensures ID_COLUMN is a non-empty string.
- **test_exclusions_file_is_string**: Ensures EXCLUSIONS_FILE is a non-empty string.

## tests/processing/test_metric_calculator.py

### metric_calculator.py
- **test_calculate_column_stats_basic**: Tests _calculate_column_stats with a simple increasing series for correct mean, min, max, latest value, change, and Z-score.
- **test_calculate_column_stats_nan**: Tests _calculate_column_stats with NaN values in the series, ensuring mean skips NaN and Z-score is handled.
- **test_calculate_column_stats_zero_std**: Tests _calculate_column_stats when all changes are the same (std=0), ensuring Z-score is 0.0.
- **test_calculate_latest_metrics_basic**: Tests calculate_latest_metrics with a DataFrame containing two funds and a benchmark, checking output columns and index.
- **test_calculate_latest_metrics_edge_cases**: Tests calculate_latest_metrics with a single data point, ensuring change and Z-score metrics are handled gracefully (NaN or float).

## tests/processing/test_curve_processing.py

### curve_processing.py
- **test_term_to_days_basic**: Tests _term_to_days with common term strings and edge cases.
- **test_load_curve_data_valid**: Mocks a valid curves.csv and checks correct DataFrame structure and term conversion.
- **test_load_curve_data_file_not_found**: Ensures load_curve_data returns an empty DataFrame if the file is missing.
- **test_get_latest_curve_date**: Checks that get_latest_curve_date returns the most recent date from a MultiIndex DataFrame.
- **test_check_curve_inconsistencies_monotonicity**: Checks that a non-monotonic drop in curve values is flagged as an inconsistency.
- **test_check_curve_inconsistencies_ok**: Checks that a monotonic increasing curve is reported as OK.

## tests/processing/test_issue_processing.py

### issue_processing.py
- **test_load_issues_valid**: Checks that a valid data_issues.csv is loaded correctly and columns are present.
- **test_load_issues_file_not_found**: Ensures loading issues from a missing file returns an empty DataFrame with required columns.
- **test_generate_issue_id**: Verifies correct ID generation for no IDs, existing IDs, and non-matching IDs.
- **test_add_issue**: Adds an issue to an empty folder and checks that it is present in the loaded issues.
- **test_close_issue**: Adds and then closes an issue, verifying the status and closure fields are updated.
- **test_load_fund_list**: Loads fund codes from FundList.csv with various column names and checks the result.

## tests/processing/test_staleness_processing.py

### staleness_processing.py
- **test_is_placeholder_value**: Checks detection of placeholder values (e.g., 'N/A', '', None) and non-placeholder values.
- **test_get_staleness_summary**: Mocks a Data folder with sec_*.csv files and checks that a staleness summary is produced for each file.
- **test_get_stale_securities_details**: Mocks a Data folder with sec_*.csv files and checks that stale securities details are produced for each file.

## tests/processing/test_attribution_processing.py

### attribution_processing.py
- **test_sum_l2s_block**: Tests sum_l2s_block with a DataFrame and checks correct L2 sums by prefix and columns.
- **test_sum_l1s_block**: Tests sum_l1s_block with a DataFrame and L1 groups, checking correct group sums.
- **test_compute_residual_block**: Tests compute_residual_block for correct residual calculation from L0 and L2 sums.
- **test_calc_residual**: Tests calc_residual for correct row-level residual calculation.
- **test_norm**: Tests norm for correct normalization and non-normalization cases.

## tests/processing/test_data_loader.py

### data_loader.py
- **test_find_column**: Tests _find_column for correct column matching and error on no match.
- **test_create_empty_dataframe**: Tests creation of an empty DataFrame with and without a benchmark column.
- **test_find_columns_for_file**: Tests detection of date, code, benchmark, and value columns from headers.
- **test_parse_date_column**: Tests robust date parsing from a DataFrame column.
- **test_convert_value_columns**: Tests conversion of value columns to float and handling of non-numeric values.
- **test_process_single_file_valid**: Tests processing of a valid CSV file with expected columns.
- **test_load_and_process_data_valid**: Tests loading and processing of a valid primary CSV file.

## tests/processing/test_security_processing.py

### security_processing.py
- **test_load_and_process_security_data_valid**: Tests loading and melting of a wide-format security CSV file, checking for correct columns and static column detection.
- **test_calculate_security_latest_metrics**: Tests calculation of latest metrics (latest value, change, mean, max, min, change Z-score) from a long-format DataFrame with MultiIndex.

## tests/processing/test_weight_processing.py

### weight_processing.py
- **test_process_weight_file_funds_and_bench**: Tests processing of w_Funds.csv and w_Bench.csv files, ensuring headers after the first column are replaced with dates from Dates.csv and the output shape is correct.
- **test_process_weight_file_w_secs**: Tests processing of w_secs.csv with dynamic metadata detection, ensuring metadata columns are preserved and data columns are replaced with dates.
- **test_process_weight_file_more_dates_than_columns**: Ensures that if there are more dates than data columns, only as many dates as columns are used.
- **test_process_weight_file_more_columns_than_dates**: Ensures that if there are more data columns than dates, only as many columns as dates are used.
- **test_process_weight_file_empty_file**: Verifies that an empty input file results in no output or an empty output file.
- **test_process_weight_file_missing_dates_csv**: Ensures that if Dates.csv is missing, the function does not produce an output file and does not raise an error.

All tests use pytest and temporary files for isolation, and mock logging to avoid clutter.

## tests/views/test_main_views.py

### main_views.py (dashboard/index route)
- **test_index_route_success**: Mocks two ts_*.csv files, simulates successful data loading and metric calculation, and checks that the response is 200 and contains expected metric names in the rendered template.
- **test_index_route_no_files**: Simulates no ts_*.csv files in the data folder, checks that the response is 200 and the template renders with empty metrics/summary.
- **test_index_route_file_load_error**: Simulates a file where data loading fails, checks that the response is 200 and the template renders with empty summary.
- **test_index_route_metrics_empty**: Simulates a file where metric calculation returns an empty DataFrame, checks that the response is 200 and the template renders with empty summary.
- **test_index_route_data_folder_missing**: Simulates FileNotFoundError for the data folder, checks that the response is 200 or 500 and the error is handled gracefully.

All tests use Flask's test client and mock dependencies for isolation. Edge and error cases are covered.

## tests/views/test_metric_views.py

### metric_views.py (/metric/<metric_name> route)
- **test_metric_page_success**: Mocks a valid metric file and data, simulates successful data loading and metric calculation, and checks that the response is 200 and contains the metric name and chart data in the rendered template.
- **test_metric_page_missing_file**: Simulates a missing metric file, checks that the response is 404 and contains an error message.
- **test_metric_page_empty_data**: Simulates a metric file with empty data, checks that the response is 500 or contains an error message about missing fund data.
- **test_metric_page_secondary_missing**: Simulates missing secondary data, checks that the response is 200 and the metric page still renders.
- **test_metric_page_metric_calc_error**: Simulates an error in metric calculation, checks that the response is 500 or contains an error message.

All tests use Flask's test client and mock dependencies for isolation. Edge and error cases are covered.

## tests/views/test_security_views.py

### security_views.py (/security/summary and /security/details/<metric_name>/<security_id> routes)
- **test_securities_page_success**: Mocks a valid security data file and metrics, simulates successful data loading, exclusion logic, and checks that the response is 200 and contains expected data in the rendered template.
- **test_securities_page_no_file**: Simulates a missing security data file, checks that the response is 200 and contains an error message.
- **test_securities_page_empty_data**: Simulates a security data file with empty data, checks that the response is 200 and contains an error message.
- **test_securities_page_empty_after_filtering**: Simulates all data filtered out (e.g., by search), checks that the response is 200 and contains a message about no securities found.
- **test_securities_page_pagination**: Simulates multiple rows for pagination, checks that the response is 200 and contains expected data for the requested page.
- **test_security_details_success**: Mocks a valid security data file for the details route, checks that the response is 200 and contains the security ID or chart data.
- **test_security_details_missing_file**: Simulates a missing file for the details route, checks that the response is 200 and contains an error message.

All tests use Flask's test client and mock dependencies for isolation. Edge and error cases are covered.

## tests/views/test_fund_views.py

### fund_views.py (/fund/<fund_code> route)
- **test_fund_detail_page_success**: Mocks file discovery (glob.glob for ts_*.csv), mocks data loading (load_and_process_data) to return a DataFrame with the fund code and datetime index, and checks that the embedded chart data JSON contains the expected metric names. This test validates that the fund detail page correctly aggregates and renders chart data for all metrics for a single fund. All assertions pass.

All tests use Flask's test client and mock dependencies.

## tests/views/test_exclusion_views.py

### exclusion_views.py (/exclusions GET, /exclusions/add POST routes)
- **test_exclusions_page_success**: Tests GET `/exclusions`, mocks loading existing exclusions, verifies 200 status and correct rendering of exclusions table and add form.
- **test_exclusions_page_no_file**: Tests GET `/exclusions` when `Exclusions.csv` is missing, verifies 200 status and rendering of a 'no exclusions found' message.
- **test_exclusions_page_load_error**: Tests GET `/exclusions` simulating a pandas error during loading, verifies 200 status, flash error message, and error content in response.
- **test_add_exclusion_success**: Tests POST `/exclusions/add` with valid ISIN/Reason, mocks file writing, verifies redirect (200 status), flash success message, and checks that `open` was called with the correct arguments and data.
- **test_add_exclusion_missing_data**: Tests POST `/exclusions/add` with missing form data, verifies 200 status, flash error message, and that file writing was not attempted.
- **test_add_exclusion_write_error**: Tests POST `/exclusions/add` simulating an `IOError` during file write, verifies 200 status, flash error message, and relevant error content.

All tests use Flask's test client and mock dependencies, including `builtins.open` for file operations.

## tests/views/test_issue_views.py

### issue_views.py (/issues GET, /issues/add POST, /issues/close/<issue_id> POST routes)
- **test_issues_page_success**: Tests GET `/issues`, mocks loading existing issues, verifies 200 status and correct rendering of issues table and add form.
- **test_issues_page_no_file**: Tests GET `/issues` when the issues file is missing, verifies 200 status and rendering of a 'no open issues found' message.
- **test_issues_page_load_error**: Tests GET `/issues` simulating a pandas error during loading, verifies 200 status, flash error message, and error content.
- **test_add_new_issue_success**: Tests POST `/issues/add` with valid data, mocks `add_issue` function, verifies redirect (200 status), flash success message, and that `add_issue` was called correctly.
- **test_add_new_issue_missing_data**: Tests POST `/issues/add` with missing form data, verifies 200 status, flash error message, and that `add_issue` was not called.
- **test_add_new_issue_save_error**: Tests POST `/issues/add` simulating `add_issue` returning False (save failure), verifies 200 status and flash error message.
- **test_close_existing_issue_success**: Tests POST `/issues/close/<id>`, mocks `close_issue` returning True, verifies redirect (200 status), flash success message, and that `close_issue` was called correctly.
- **test_close_existing_issue_failure**: Tests POST `/issues/close/<id>`, mocks `close_issue` returning False (e.g., issue not found), verifies 200 status and flash error message.

All tests use Flask's test client and mock dependencies for issue processing functions.

## tests/views/test_curve_views.py

### curve_views.py (/curve route)
- **test_curve_page_success**: Mocks successful loading of curve data and inconsistency checks, verifies 200 status, template content (title, date, inconsistency table, plot div).
- **test_curve_page_no_data_file**: Simulates the curve file not existing, verifies graceful handling (200 status) and appropriate flash message/content indicating the missing file.
- **test_curve_page_load_error**: Simulates `FileNotFoundError` during `load_curve_data`, verifies graceful handling (200 status) and an error message.
- **test_curve_page_processing_error**: Simulates `ValueError` during `check_curve_inconsistencies`, verifies 200 status (page still renders chart) and an error message about inconsistency check failure.

All tests use Flask's test client and mock dependencies.

## tests/views/test_attribution_views.py

### attribution_views.py (/attribution route)
- **test_attribution_page_success**: Mocks successful data loading and calculations (metrics, residuals, normalization), verifies 200 status, template content (title, tables, plot div).
- **test_attribution_page_no_data**: Simulates `FileNotFoundError` during data loading, verifies graceful handling (200 status) and appropriate flash message/content indicating missing data.
- **test_attribution_page_processing_error**: Simulates `ValueError` during `calc_residual`, verifies graceful handling (200 status) and an error message about residual calculation failure.

All tests use Flask's test client and mock dependencies.

## tests/views/test_staleness_views.py

### staleness_views.py (/staleness route)
- **test_staleness_page_success**: Mocks successful retrieval of staleness summary, details, and plot creation, verifies 200 status and rendering of summary/details tables and plot div.
- **test_staleness_page_no_data**: Simulates `FileNotFoundError` during `get_staleness_summary`, verifies graceful handling (200 status) and appropriate flash message/content indicating missing data.
- **test_staleness_page_processing_error**: Simulates `ValueError` during `get_stale_securities_details`, verifies graceful handling (200 status) and an error message about processing failure.

All tests use Flask's test client and mock dependencies.

## tests/views/test_weight_views.py

### weight_views.py (/weights route)
- **test_weights_page_success**: Mocks successful loading of weights data, verifies 200 status, template content (title, date, table data).
- **test_weights_page_no_data_file**: Simulates the weight file not existing, verifies graceful handling (200 status) and appropriate flash message/content indicating the missing file.
- **test_weights_page_load_error**: Simulates `FileNotFoundError` during `load_weights_and_held_status`, verifies graceful handling (200 status) and an error message.

All tests use Flask's test client and mock dependencies.
