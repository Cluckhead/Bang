**Important Note on Date Formats:**

Throughout this application, date processing logic (especially when identifying date columns in input files) is now fully flexible. The loader will handle common formats like `YYYY-MM-DD`, `DD/MM/YYYY`, and ISO 8601 (`YYYY-MM-DDTHH:MM:SS`) where appropriate, particularly during initial data loading and column identification steps. If a date cannot be parsed with these, pandas' flexible parser is used as a final fallback. This ensures robust handling of a wide variety of date formats in your data files.

ISIN is used as the primary identifier for securities, and is stored in the `w_secs.csv` file.

---

# Simple Data Checker

This application provides a web interface to load, process, and check financial data, primarily focusing on time-series metrics and security-level data. It helps identify potential data anomalies by calculating changes and Z-scores.

## Features

| Feature                     | Description / Key Routes / Notes                                                                                  |
|-----------------------------|------------------------------------------------------------------------------------------------------------------|
| **Time-Series Metric Analysis** | Load `ts_*.csv`, view changes, Z-scores, charts. Route: `/metric/<metric_name>`. S&P toggles for valid/comparison data. |
| **Security-Level Analysis**      | Load `sec_*.csv`, view changes/Z-scores, charts for YTM/YTW/Duration/Spread. Routes: `/security/summary`, `/security/details/<metric_name>/<security_id>`. |
| **Generic Data Comparison**      | Compare pairs of security datasets (e.g., Spread vs SpreadSP). Configurable via `COMPARISON_CONFIG`. Routes: `/compare/<type>/summary`, `/compare/<type>/details/<security_id>`. Fund holdings table included. |
| **Fund-Specific Views**          | `/fund/<fund_code>` (overview), `/fund/duration_details/<fund_code>` (duration details).                      |
| **Security Exclusions**          | Manage via `/exclusions` (`Data/exclusions.csv`).                                                            |
| **Data Issue Tracking**          | Log/manage via `/issues` (`Data/data_issues.csv`). User dropdowns, Jira link.                                 |
| **Weight Check**                 | Compare fund/benchmark weights via `/weights/check`.                                                         |
| **Yield Curve Analysis**         | Check curve inconsistencies via `/curve/summary`, `/curve/details/<currency>`. Highlights staleness/missing data. |
| **Attribution Residuals**        | Analyze via `/attribution`. 3-way toggle (L0/L1/L2), per-fund files, color-coded.                            |
| **Data Simulation**              | API simulation via `/get_data`.                                                                              |
| **Special Character Handling**   | Security IDs URL-encoded/decoded.                                                                            |
| **Max/Min Value Breach**         | Checks `sec_*.csv` against thresholds. Dashboard: `/maxmin/dashboard`. Details: `/maxmin/details/<file>/<type>`. |
| **Watchlist Management**         | Track/add/clear securities via `/watchlist`. Filterable, auditable, modal UI.                                |
| **Inspect (Contribution Analysis)**      | Analyze top contributors/detractors to metric changes over a date range. Modal UI, supports all analytics. See below for technical details. |

## Fund Group Filtering (Reusable Feature)

| Aspect         | Details                                                                                      |
|----------------|---------------------------------------------------------------------------------------------|
| **Available On** | Metric Detail, Security Summary, All Comparison Summary pages                              |
| **UI**           | Dropdown of fund groups above main filter form; only groups with data shown                |
| **Behavior**     | Selecting a group filters to those funds/benchmarks; persists via URL query param          |
| **Server-side**  | Filtering, sorting, and pagination are all server-side                                     |
| **Comparison Pages** | Uses `parse_fund_list` to match funds in group                                         |
| **Reusable**     | Logic and dropdown available for all comparison types in `config.py`                       |

**How to Reuse:**
- Load fund groups: `utils.load_fund_groups(data_folder)`
- Get selected group: `selected_fund_group = request.args.get('fund_group', None)`
- Filter data: Only include funds in `fund_groups[selected_fund_group]`
- Pass to template: `fund_groups`, `selected_fund_group`
- Render UI: Use dropdown pattern (see `metric_page_js.html`)
- Persistence: State is in URL/query string

## File Structure Overview

### Python Core Modules
```mermaid
graph TD
    A[app.py]
    B[data_loader.py]
    C[metric_calculator.py]
    D[security_processing.py]
    E[process_data.py]
    F[curve_processing.py]
    G[issue_processing.py]
    H[weight_processing.py]
    I[data_validation.py]
    J[process_w_secs.py]
    K[process_weights.py]
    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    A --> J
    A --> K
```

### Views
```mermaid
graph TD
    A[main_views.py]
    B[metric_views.py]
    C[security_views.py]
    D[fund_views.py]
    E[exclusion_views.py]
    F[weight_views.py]
    G[api_views.py]
    H[curve_views.py]
    I[issue_views.py]
    J[attribution_views.py]
    K[generic_comparison_views.py]
    L[maxmin_views.py]
    M[watchlist_views.py]
    G --> G1[api_core.py]
    G --> G2[api_routes_data.py]
    G --> G3[api_routes_call.py]
```

### Templates
```mermaid
graph TD
    A[base.html]
    B[index.html]
    C[metric_page_js.html]
    D[securities_page.html]
    E[security_details_page.html]
    F[fund_duration_details.html]
    G[exclusions_page.html]
    H[get_data.html]
    I[fund_detail_page.html]
    J[weight_check.html]
    K[curve_summary.html]
    L[curve_details.html]
    M[issues_page.html]
    N[attribution_summary.html]
    O[comparison_summary_base.html]
    P[comparison_details_base.html]
    Q[maxmin_dashboard.html]
    R[maxmin_details.html]
    S[watchlist_page.html]
```

### Static Files
```mermaid
graph TD
    A[js/]
    B[modules/]
    B1[ui/]
    B2[utils/]
    B3[charts/]
    B1a[chartRenderer.js]
    B1b[securityTableFilter.js]
    B1c[tableSorter.js]
    B1d[toggleSwitchHandler.js]
    B2a[helpers.js]
    B3a[timeSeriesChart.js]
    A --> B
    B --> B1
    B --> B2
    B --> B3
    B1 --> B1a
    B1 --> B1b
    B1 --> B1c
    B1 --> B1d
    B2 --> B2a
    B3 --> B3a
```

### Config/Utils
```mermaid
graph TD
    A[config.py]
    B[utils.py]
```

## Application Components

### Data Files (`Data/`)

| File | Description |
|------|-------------|
| `ts_*.csv` | Time-series data indexed by Date and Code (Fund/Benchmark) |
| `sp_ts_*.csv` | (Optional) Secondary/comparison time-series data corresponding to `ts_*.csv` |
| `sec_*.csv` | Security-level data in wide format (dates as columns). Used for Securities Check and Comparisons. Date parsing is fully flexible: supports `YYYY-MM-DD`, `DD/MM/YYYY`, and ISO 8601 (`YYYY-MM-DDTHH:MM:SS`), with pandas fallback for any others. |
| `pre_*.csv` | Input files for the `process_data.py` script |
| `new_*.csv` | Output files from the `process_data.py` script |
| `exclusions.csv` | Excluded securities list (`SecurityID`, `AddDate`, `EndDate`, `Comment`) |
| `QueryMap.csv` | Maps query IDs to filenames for API simulation |
| `FundList.csv` | Fund codes and metadata for the API simulation page |
| `Dates.csv` | Configuration data for specific use cases |
| `w_Funds.csv` | Daily fund weights (expected to be 100%) |
| `w_Bench.csv` | Daily benchmark weights (expected to be 100%) |
| `w_secs.csv` | Security weights with ISIN as primary identifier. Used to determine currently held securities. |
| `curves.csv` | Yield curve data (Date, Currency Code, Term, Daily Value) |
| `data_issues.csv` | Issue tracking log (ID, dates, users, details, resolution, Jira link) |
| `att_factors.csv` | Attribution data with L0, L2 factors for Production and S&P. **Note:** The `L0 Total` column represents the returns for each security/fund/date. |
| `users.csv` | List of users for issue tracking dropdowns (`Name` column) |
| `att_factors_<FUNDCODE>.csv` | Attribution data for a specific fund, used by all attribution dashboards. Replaces the single `att_factors.csv` file. | Used by `/attribution/summary`, `/attribution/security`, `/attribution/radar`, `/attribution/charts` |
| `sec_YTM.csv`, `sec_YTMSP.csv`, `sec_YTW.csv`, `sec_YTWSP.csv` | Security-level YTM and YTW data (main and S&P overlays), used for new charts on the security details page. |

### Python Core Modules

| File | Purpose | Key Functions |
|------|---------|--------------|
| `app.py` | Application entry point using Flask factory pattern | `create_app()`, `run_cleanup()` |
| `config.py` | Configuration variables | `DATA_FOLDER`, `COLOR_PALETTE`, `COMPARISON_CONFIG` |
| `data_loader.py` | Load and preprocess time-series data | `load_and_process_data()`, `_find_column()` |
| `metric_calculator.py` | Calculate statistical metrics | `calculate_latest_metrics()`, `_calculate_column_stats()` |
| `process_data.py` | Preprocess CSV files | `process_csv_file()`, `main()` |
| `security_processing.py` | Process security-level data | `load_and_process_security_data()`, `calculate_security_latest_metrics()` |
| `utils.py` | Utility functions | `_is_date_like()`, `parse_fund_list()`, `load_weights_and_held_status()` |
| `curve_processing.py` | Process yield curve data | `load_curve_data()`, `check_curve_inconsistencies()` |
| `issue_processing.py` | Manage data issues (load, add, close) using `data_issues.csv` and `users.csv` | `add_issue()`, `close_issue()`, `load_issues()` |
| `weight_processing.py` | Process and clean weight files, replacing generic headers with dates from Dates.csv for fund, benchmark, and security weights. | `process_weight_file()` |
| `process_weights.py` | Batch process all weight files in Data/, converting pre_w_*.csv to w_*.csv with correct date headers. | `main()`, `process_weight_file_with_reversed_dates()`, `process_securities_file()` |
| `process_w_secs.py` | Process pre_w_secs.csv to w_secs.csv, replacing weight columns with dates and preserving metadata columns. | `process_securities_file()` |
| `data_validation.py` | Validate structure and content of DataFrames before saving, checking columns and types by file type. | `validate_data()` |

## Logging and Diagnostics

The Simple Data Checker uses a **centralized logging system** to capture application events, errors, and diagnostics. This makes it easy to trace issues and monitor application health, both during development and in production.

### How Logging Works (Step by Step)

1. **Centralized Setup in `app.py`**
   - Logging is configured in the Flask application factory (`create_app`).
   - Both a **rotating file handler** (writes logs to `instance/app.log`) and a **console handler** (prints to terminal) are set up.
   - The log format includes timestamps, log level, message, and source location for clarity.
   - Log level is set to `DEBUG` for the file and `DEBUG` (or `INFO`) for the console by default.

   Example (see `app.py`):
   ```python
   # In app.py (inside create_app)
   import logging
   from logging.handlers import RotatingFileHandler

   app.logger.handlers.clear()
   app.logger.setLevel(logging.DEBUG)
   log_formatter = logging.Formatter(
       '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
   )
   file_handler = RotatingFileHandler('instance/app.log', maxBytes=10*1024*1024, backupCount=5)
   file_handler.setFormatter(log_formatter)
   file_handler.setLevel(logging.DEBUG)
   app.logger.addHandler(file_handler)
   console_handler = logging.StreamHandler()
   console_handler.setFormatter(log_formatter)
   console_handler.setLevel(logging.DEBUG)
   app.logger.addHandler(console_handler)
   ```

2. **Module-Level Logging**
   - Each Python module gets its own logger using `logging.getLogger(__name__)`.
   - This ensures log messages are tagged with the module name, making it easy to trace their origin.
   - Do **not** call `basicConfig` or set up handlers in individual modules—use the centralized config.

   Example usage in a module:
   ```python
   import logging
   logger = logging.getLogger(__name__)

   def some_function():
       logger.info("Processing started.")
       try:
           # ... code ...
       except Exception as e:
           logger.error(f"Error occurred: {e}", exc_info=True)
   ```

3. **Log File Location**
   - All logs are written to `instance/app.log` (rotated when large).
   - Console output is also available for real-time monitoring during development.

4. **Log Levels**
   - Use `logger.debug()` for verbose output, `logger.info()` for general events, `logger.warning()` for recoverable issues, and `logger.error()` for errors.
   - For critical failures, use `logger.critical()`.

5. **Extending Logging in New Modules**
   - Always use `logger = logging.getLogger(__name__)` at the top of new modules.
   - Use the logger for all diagnostic, warning, and error messages.
   - Avoid configuring handlers or formatters in new modules—this is handled centrally.

6. **Changing Log Levels or Format**
   - To adjust log verbosity or format, edit the logging setup in `app.py` or the `LOGGING_CONFIG` in `config.py`.
   - For production, consider setting the console handler to `INFO` or `WARNING` to reduce noise.

### Example: Adding Logging to a New Module

```python
import logging
logger = logging.getLogger(__name__)

def do_something():
    logger.info("Started task.")
    try:
        # ...
    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
```

This approach ensures all logs are consistent, easy to find, and follow a standard format across the application.

### View Modules (`views/`)

| Module | Purpose | Routes |
|--------|---------|--------|
| `main_views.py` | Main dashboard | `/` |
| `metric_views.py` | Time-series metric details | `/metric/<metric_name>` |
| `security_views.py` | Security-level data checks | `/security/summary`, `/security/details/<metric_name>/<security_id>` |
| `fund_views.py` | Fund-specific views | `/fund/<fund_code>`, `/fund/duration_details/<fund_code>` |
| `exclusion_views.py` | Security exclusion management | `/exclusions`, `/exclusions/remove` |
| `generic_comparison_views.py` | **Generic comparison of two security datasets (e.g., Spread, Duration). Loads data, calculates stats, handles filtering/sorting/pagination for summary, and prepares data (including fund holdings from `w_secs.csv`) for detail view.** | `/compare/<comparison_type>/summary`, `/compare/<comparison_type>/details/<security_id>` |
| `api_views.py` | API simulation | `/get_data`, `/run-api-calls`, `/rerun-api-call` |
| `weight_views.py` | Weight checking | `/weights/check` |
| `curve_views.py` | Yield curve checking | `/curve/summary`, `/curve/details/<currency>` |
| `issue_views.py` | Issue tracking | `/issues`, `/issues/close` |
| `attribution_views.py` | Attribution analysis | `/attribution` |
| `maxmin_views.py` | Max/Min value breach checking | `/maxmin/dashboard`, `/maxmin/details/<file_name>/<breach_type>` |
| `watchlist_views.py` | **Watchlist management: add, clear, and audit securities of interest. Uses CSV storage and pandas for data.** | `/watchlist` |

### HTML Templates (`templates/`)

| Template | Purpose | Key Features |
|----------|---------|-------------|
| `base.html` | Main layout | Bootstrap, navbar, common structure |
| `index.html` | Dashboard | Metric links, Z-Score summary table |
| `metric_page_js.html` | Time-series detail page | Toggle switch for SP data |
| `securities_page.html` | Security summary table | Filter/search form, pagination |
| `security_details_page.html` | Security detail page | Multiple charts (Value, Price, Duration) |
| `fund_duration_details.html` | Fund duration details | Security duration changes table |
| `exclusions_page.html` | Exclusion management | Add/remove security exclusions |
| `get_data.html` | API simulation | Data status, fund selection, date inputs |
| `comparison_summary_base.html` | **Generic comparison summary page** | Filter form, sortable table, pagination |
| `comparison_details_base.html` | **Generic comparison details page** | Side-by-side charts, statistics display, **fund holdings over time table** |
| `fund_detail_page.html` | Fund metrics overview | Multiple charts with SP data toggle |
| `weight_check.html` | Weight checking | Fund/benchmark weight comparison |
| `curve_summary.html` | Yield curve summary | Inconsistency check table |
| `curve_details.html` | Yield curve details | Chart.js line chart with date selector |
| `issues_page.html` | Issue tracking | Add/view/close issue forms and tables, user dropdowns, Jira link field |
| `attribution_summary.html` | Attribution summary | Multiple detail levels with comparison data |
| `maxmin_dashboard.html` | Max/Min breach summary | Cards summarizing breaches per file |
| `maxmin_details.html` | Max/Min breach details | Table listing breaching securities |
| `watchlist_page.html` | **Watchlist UI: Add/clear modal, filterable/scrollable security list, autofill prevention, user/reason tracking.** | Add to Watchlist modal, filter/search, audit trail |

### JavaScript Files (`static/js/`)

| File | Purpose | Key Features |
|------|---------|-------------|
| `main.js` | Main JS entry point | Initializes components |
| `modules/ui/chartRenderer.js` | Render charts | Time-series, comparison charts |
| `modules/ui/securityTableFilter.js` | Handle table filtering | Dynamic filter application |
| `modules/ui/tableSorter.js` | Handle table sorting | Sort direction toggle |
| `modules/ui/toggleSwitchHandler.js` | Handle toggle switches | Show/hide comparison data |
| `modules/utils/helpers.js` | Utility functions | Common helper methods |
| `modules/charts/timeSeriesChart.js` | Time-series chart creation | Chart.js configuration |

### Attribution Data Calculation

Attribution residuals are calculated using the following formulas:
- `L0 Total = L1 Rates Total + L1 Credit Total + L1 FX Total + L1 Residual`
- `L1 Rates Total = L2 Rates Carry Daily + L2 Rates Convexity Daily + L2 Rates Curve Daily + L2 Rates Duration Daily + L2 Rates Roll Daily`
- `L1 Credit Total = L2 Credit Carry Daily + L2 Credit Convexity Daily + L2 Credit Defaulted Daily + L2 Credit Spread Change Daily`
- `L1 FX Total = L2 FX Carry Daily + L2 FX Change Daily`
- `L1 Residual = L0 Total - (L1 Rates + L1 Credit + L1 FX)`
- Perfect attribution is achieved when residual = 0

## Adding a New Comparison Type

Thanks to the refactored generic comparison framework, adding a new comparison (e.g., Yield vs YieldSP) is straightforward:

1.  **Ensure Data Files Exist:** Make sure the two security-level data files you want to compare exist in the `Data/` folder and follow the standard wide format (e.g., `Data/sec_yield.csv` and `Data/sec_yieldSP.csv`). They should have dates as columns and include an identifier column (like `ISIN`) and any relevant static attribute columns (like `Type`, `Currency`).
2.  **Update Configuration:** Open `config.py` and add a new entry to the `COMPARISON_CONFIG` dictionary. The key will be used in the URL (e.g., `'yield'`). The value should be a dictionary containing:
    *   `'display_name'`: The user-friendly name (e.g., `'Yield'`).
    *   `'file1'`: The filename of the first dataset (e.g., `'sec_yield.csv'`).
    *   `'file2'`: The filename of the second dataset (e.g., `'sec_yieldSP.csv'`).
    *   `'value_label'`: The label to use for the data value on charts and axes (e.g., `'Yield'`).

    ```python
    # Example entry in config.py
    COMPARISON_CONFIG = {
        # ... existing entries ...
        'yield': {
            'display_name': 'Yield',
            'file1': 'sec_yield.csv',
            'file2': 'sec_yieldSP.csv',
            'value_label': 'Yield'
        }
    }
    ```

3.  **Update Navigation:** Open `templates/base.html` and add a new list item (`<li>`) within the "Comparisons" dropdown section of the navigation bar. Point the link to the new summary page using `url_for`:

    ```html
    <li><a class="dropdown-item" href="{{ url_for('generic_comparison_bp.summary', comparison_type='yield') }}">Yield Comparison</a></li>
    ```

That's it! The `generic_comparison_views.py` module and the base templates (`comparison_summary_base.html`, `comparison_details_base.html`) will automatically handle the routing, data loading, statistics calculation, filtering, sorting, pagination, and rendering for the new comparison type based on the configuration.

### Security Details Page (Technical Details)

- The security details page now displays all static columns from `reference.csv` in a grouped tile on the left (Identifiers, Classification, Financials, etc.), with all time-series charts on the right in a two-column layout.
- Exclusion status (if the security is on the exclusion list) and open data issues (if any) are shown in bold red in the static tile, with all open issues listed.
- A Bloomberg YAS link is generated for each security using the 'BBG Ticker Yellow' field. The link format is now configurable via the `BLOOMBERG_YAS_URL_FORMAT` variable in `config.py`, making it easy to change or reuse the link format elsewhere in the app.

### Inspect (Contribution Analysis) Feature (Technical Details)

The Inspect (Contribution Analysis) feature enables root-cause analysis of changes in any time-series metric (e.g., Duration, Spread, YTM, Spread Duration) at the security level. It is accessible from each chart on the metric detail page.

**Workflow:**
- Each chart includes an **Inspect** button.
- Clicking opens a modal for user input:
  - **Date Range:** User selects a subset of the chart's date range.
  - **Data Category:** User selects "Original" or "SP" (S&P) data source.
- On submission, the backend calculates contributions for each security:
  - Loads weights from `w_secs.csv` and metric values from `sec_<metric>.csv` or `sp_sec_<metric>.csv`.
  - For each security and day in the range: `Contribution = Weight × MetricValue`.
  - Computes the average contribution over the range and compares to the baseline (day before the range).
  - Ranks securities by the change; shows top 10 contributors and top 10 detractors.
- Results are displayed in a dedicated results page, with links to security details.

**Implementation:**
- **Backend:**
  - Main logic in `views/metric_views.py`:
    - `_calculate_contributions(metric_name, fund_code, start_date_str, end_date_str, data_source, top_n=10)`
    - Routes: `/metric/<metric_name>/inspect` (POST), `/metric/inspect/results` (GET)
  - Handles flexible date parsing, missing data, and merges static info from `reference.csv`.
- **Frontend:**
  - Modal UI for input selection (date range, data source).
  - Results page lists contributors/detractors with links.
- **Supported Metrics:**
  - Duration, Spread, YTM, Spread Duration, and any metric with security-level data.

**Key Files and Functions:**
- `views/metric_views.py` (core logic and routes)
- `w_secs.csv` (weights)
- `sec_<metric>.csv`, `sp_sec_<metric>.csv` (metric values)
- `reference.csv` (static security info)

**Example Calculation:**
- For each security:
  - For each day in range: `contribution = weight × metric_value`
  - Average over range: `avg_contribution = sum(contributions) / N_days`
  - Baseline: contribution on day before range
  - Change: `avg_contribution - baseline`
- Top 10 positive and negative changes are shown as contributors/detractors.

**Purpose:**
- Quickly identify which securities are driving changes in portfolio analytics over any period.
- Integrated, user-friendly workflow for root-cause analysis.