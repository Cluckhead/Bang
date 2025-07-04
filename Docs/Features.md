# Application Features

## Table of Contents
- [Date Parsing Flexibility](#date-parsing-flexibility)
- [File Audit & Consistency Checker (NEW)](#file-audit--consistency-checker-new)
- [Generic Data Comparison](#generic-data-comparison)
- [Data Staleness Detection](#data-staleness-detection)
- [Security-Level Analysis: Min=0 Exclusion Toggle](#security-level-analysis-min0-exclusion-toggle)
- [Security-Level Analysis: Volatility Metrics & 'Mark Good' (NEW)](#security-level-analysis-volatility-metrics--mark-good-new)
- [Security-Level Analysis: Duration Data Check (NEW)](#security-level-analysis-duration-data-check-new)
- [Security Data Override Modal (NEW)](#security-data-override-modal-new)
- [Security-Level Analysis](#security-level-analysis)
- [Views and Functionality](#views-and-functionality)
- [Technical Details](#technical-details)
- [Security Details Page Enhancements](#security-details-page-enhancements)
- [Watchlist Feature](#watchlist-feature)
- [Inspect (Contribution Analysis) Feature](#inspect-contribution-analysis-feature)
- [Attribution Data API (NEW)](#attribution-data-api-new)
- [Config-Driven Metric Details Pages (May 2025)](#config-driven-metric-details-pages-may-2025)
- [Individual Security Attribution Time Series (NEW)](#individual-security-attribution-time-series-new)

---

## Date Parsing Flexibility

All security-level and time-series data loaders now support fully flexible date parsing. The application will handle `YYYY-MM-DD`, `DD/MM/YYYY`, and ISO 8601 (`YYYY-MM-DDTHH:MM:SS`) formats, with pandas' flexible parser as a final fallback for any other date formats. This ensures robust handling of a wide variety of date formats in your data files.

---

## File Audit & Consistency Checker (NEW)

The File Audit feature provides a comprehensive, automated review of all key data files in the application. It is accessible from the `/get_data` page and produces a detailed, actionable report.

### What It Checks
- **Date Range Consistency:**
  - Checks that all files of the same type (e.g., all `ts_*.csv`, all `sec_*.csv`, all key files like `w_Bench.csv`, `w_Funds.csv`, `w_secs.csv`, `att_factors.csv`, `curves.csv`) cover the same date range.
  - Highlights any files whose date ranges are out of sync with the majority.
- **File Structure Issues:**
  - Detects missing headers, blank columns, files with only headers, and columns that are entirely blank.
  - Flags files that cannot be read or parsed.
- **Format-Aware:**
  - Supports both **wide format** (dates as columns, e.g., `w_Bench.csv`, `sec_*.csv`) and **long format** (date in a column, e.g., `ts_*.csv`, `curves.csv`).
  - Automatically detects the correct date column or columns for each file.
- **Key Files Always Checked:**
  - Explicitly includes `w_Bench.csv`, `w_Funds.csv`, `w_secs.csv`, `att_factors.csv`, and `curves.csv` in every audit, regardless of filename prefix.
- **Summary Table:**
  - Shows file name, size, number of rows/columns, fund column, detected date range, and any issues for each file.
  - Provides actionable recommendations for fixing detected problems.
- **Skipped Files:**
  - Lists any `.csv` files in the data folder that were not included in the audit, for transparency.

### How to Use
- Go to the `/get_data` page and click the **Run Data Consistency Audit** button.
- Review the summary and details, including:
  - Date range mismatches (with expected and actual ranges)
  - Structure issues and recommendations
  - Diagnostics for all key files

### Why This Matters
- Ensures all your data files are aligned and ready for analysis.
- Quickly identifies subtle misalignments or missing data that could cause downstream errors.
- Makes it easy to spot and fix issues before running further processing or analysis.

## Attribution Data API (NEW)

The Attribution Data API feature allows users to fetch, update, and manage attribution data for each fund individually, using a dedicated UI and per-fund files. This ensures attribution analytics are always up-to-date and modular.

### Key Capabilities
- **Per-Fund Attribution Files:**
  - Each fund's attribution data is stored in a separate file: `att_factors_<FUNDCODE>.csv` (e.g., `att_factors_IG01.csv`).
  - This replaces the old single-file approach and enables more granular updates and analysis.
- **Dedicated UI:**
  - Accessed via the dashboard tile or navigation menu as "Get Attribution Data".
  - Shows a status table for all attribution files (file name, last modified, row count, latest date).
  - Users can select funds (with group support), date range, and write mode (append or redo/overwrite).
  - The form is consistent with the API simulation page, using Tailwind CSS and modern UX patterns.
- **API Call Logic:**
  - For each selected fund, the app makes a separate API call (simulated or real) using the QueryID from `QueryMap_Att.csv`.
  - Results are written to the corresponding `att_factors_<FUNDCODE>.csv` file.
- **Write Modes:**
  - **Append:** Adds new data to the file, then deduplicates by ISIN, Fund, and Date (keeping the most recent row).
  - **Redo (Overwrite):** Replaces the file entirely. A custom modal warns the user before proceeding.
- **Status Feedback:**
  - After processing, a dynamic status table shows the result for each fund (success, error, rows written).
- **Integration:**
  - All attribution dashboards and analytics now load data from these per-fund files.
  - If a file is missing, the UI shows "No attribution available." for that fund.

### Why This Matters
- Enables targeted, efficient updates to attribution data.
- Reduces risk of accidental data loss or cross-fund contamination.
- Provides clear, auditable workflow for attribution data management.
- Fully integrated with the application's fund selection, group filtering, and status reporting features.

---

## Generic Data Comparison

This feature allows users to compare two related security-level datasets side-by-side. It's configured via the `COMPARISON_CONFIG` dictionary in `config.py`.

**Available Comparison Types:**
- Spread vs SpreadSP
- Duration vs DurationSP
- Spread Duration vs Spread DurationSP
- **YTM vs YTMSP**
- **YTW vs YTWSP**

### Summary View (`/compare/<comparison_type>/summary`)

- Displays a table summarizing comparison statistics for multiple securities.
- Calculates metrics like Level Correlation, Change Correlation, Mean Absolute Difference, and Max Absolute Difference between the two datasets for each security.
- Integrates with `w_secs.csv` to show the current held status (`is_held`).
- Supports:
  - Server-side **filtering** based on static security attributes (e.g., Currency, Type) and held status (toggle to show/hide sold securities).
  - Server-side **sorting** by any column.
  - Server-side **pagination** to handle large datasets.

### Detail View (`/compare/<comparison_type>/details/<security_id>`)

- Provides an in-depth look at the comparison for a single security.
- Displays an overlayed **time-series chart** showing the values from both datasets over time.
- Shows detailed **comparison statistics** specific to that security.
- Lists other relevant **static attributes** for the security.
- **Fund Holdings Table:**
  - Displays a table below the main chart showing which funds held the selected security over the specific date range covered by the chart.
  - **Data Source:** Uses the `w_secs.csv` file, linking on the security identifier (typically ISIN).
  - **Date Alignment:** The columns in the table correspond directly to the dates shown on the x-axis of the time-series chart above it.
  - **Color Coding:**
    - `Green`: Indicates the security was held by the fund on that specific date (value in `w_secs.csv` is numeric and > 0).
    - `Red`: Indicates the security was *not* held by the fund on that date (value in `w_secs.csv` is non-numeric, blank, zero, or NaN).
  - **Funds:** Rows represent the different fund codes (`Funds` column in `w_secs.csv`) found holding the security.
- **Data Issue Tracking:** Log, view, and manage data issues via `/issues` (stored in `Data/data_issues.csv`)
  - Uses `Data/users.csv` to populate dropdowns for 'Raised By' and 'Closed By'.
  - Includes an optional 'Jira Link' field (accepts text, including URLs without `http://`) for tracking external tickets.
  - Provides 'All Funds' and 'No Funds' options in the fund selector.
  - Added 'Rimes' as a potential data source.
- **Weight Check:** Compare fund and benchmark weights via `/weights/check`

**Note:** YTM and YTW comparisons are now available in the navigation and behave identically to other comparison types. Simply select "YTM Comparison" or "YTW Comparison" from the Checks & Comparisons menu to access these features.

---

## Data Staleness Detection

This feature monitors and identifies stale or missing data in security and curve files, helping users maintain data quality and reliability.

### Core Functionality (`staleness_processing.py`)

- **File Processing:** Automatically processes files with naming pattern `sec_*.csv`, `sp_sec_*.csv`, and yield curve files in the configured data folder.
- **Detection Methods:**
  - **Placeholder Pattern Detection:** Identifies consecutive placeholder values (default: repeated values of 100) that indicate stale or missing data.
  - **Time-based Staleness:** Flags securities or curves where the last valid update is older than a configurable threshold (default: 5 days).
- **Customizable Configuration:**
  - Configurable placeholder values that indicate stale data
  - Adjustable threshold for consecutive placeholders (default: 3)
  - Configurable day threshold for time-based staleness (default: 5 days)
- **Exclusion Support:** Ability to exclude specific securities from staleness analysis

### Summary View (`/staleness/summary`)

- Displays a table summarizing staleness statistics across all processed files
- Shows metrics including:
  - Latest date in each file
  - Total securities count
  - Count and percentage of stale securities
  - Quick access to detailed views

### Detail View (`/staleness/details/<file_name>`)

- Provides an in-depth look at stale securities in a specific file
- Lists each stale security with:
  - Security ID and metadata (Name, Type, Currency, etc.)
  - Last update date
  - Days stale
  - Staleness type (placeholder pattern or time-based)
  - Number of consecutive placeholders (if applicable)

---

## Security-Level Analysis: Min=0 Exclusion Toggle

- The Securities summary page includes a toggle labeled "Exclude securities where Min = 0".
- This toggle is checked by default, and when enabled, all securities with a Min value of 0 are excluded from the results table.
- The toggle is part of the filter form and is applied server-side for accurate filtering and pagination.
- Changing the toggle automatically refreshes the page and reapplies the filter, providing instant feedback without needing to click the "Apply Filters" button.
- The toggle state is preserved across filter and sort actions.
- Add the static data to the security details page
- **Date parsing is fully flexible:** Security-level data now supports `YYYY-MM-DD`, `DD/MM/YYYY`, and ISO 8601 (`YYYY-MM-DDTHH:MM:SS`), with pandas fallback for any others.

---

## Security-Level Analysis: Volatility Metrics & 'Mark Good' (NEW)

To help analysts focus on genuinely suspect data the application now provides **two volatility-based columns** on the *Securities summary* table and a **one-click "Mark Good" mechanism** in the security details view.

### 1. Volatility Screening Columns

| Column | Meaning | Config |
|--------|---------|--------|
| **Max \|Δ\| (bps)** | Largest *absolute* day-on-day move seen over the full history.| n/a (calculated on load) |
| **% Days >| 50 bps |** | Share of trading days whose absolute move exceeded the **danger threshold** (default 50 bps). | Threshold set in `config.LARGE_MOVE_THRESHOLD_BPS`. |

These metrics flag "noisy" series where Z-scores may be suppressed by extended flat periods.

*Rows whose **latest spread** is between −10 bps and +10 bps (typically Treasuries) are automatically excluded from orange/red highlight so the grid concentrates on credit issues.*

### 2. One-Click "Mark Good" Dismiss

When a spike or dip is deemed legitimate you can remove it from future checks in **two clicks**:

1. Open the security's details page (via its ISIN link) → the main *Spread* chart appears.
2. Hover the offending point and **left-click** → confirm the browser prompt.

The app sends a POST to `/security/mark_good` and appends the trio `(ISIN, Metric, Date)` to `Data/good_points.csv`.  On reload the value is treated as *blank* and ignored in all stats, colours and Z-scores.

There is no need to restart the server; the override is applied the next time the file is loaded.

---

## Security-Level Analysis: Duration Data Check (NEW)

With the **metric-aware** security summary page you can now perform the same anomaly checks on **Duration** that previously existed only for Spread.

### Access

* **Route** – `/security/summary/Duration`
* **Navigation** – Sidebar → *Security Analysis* → *Securities – Duration*

### What's Included

* All the filters, sorting, pagination and **fund-group dropdown** present in the Spread view.
* The two **volatility columns** (*Max |Δ|* and *% Days >| 50 bps |*) and the **Min = 0 exclusion toggle*.
* The one-click **"Mark Good"** dismiss now works for **every metric**; a click on any point of the primary chart (Duration here) writes `(ISIN, "Duration", Date)` to `Data/good_points.csv`.

### How It Works

Internally the `/security/summary` route is now parameterised.  If no metric is supplied it defaults to *Spread*; pass any metric key (capitalised) and the view loads `sec_<Metric>.csv` dynamically.

```text
Spread   → /security/summary            → sec_Spread.csv
Duration → /security/summary/Duration   → sec_Duration.csv
```

This design means future metrics (e.g. *YTM*) can be enabled instantly by linking to `/security/summary/YTM` – no extra backend code needed.

---

## Security Data Override Modal (NEW)

This feature allows analysts to quickly correct or overwrite any value in the raw `sec_*` or `sec_*SP` security-level CSVs **without touching the files directly**.

### Quick Facts
* **Access:** In the Security Details page (`/security/details/<metric>/<ISIN>`) press the new **Edit&nbsp;Data** button (beside *Raise Issue* / *Add Exclusion*).
* **What you can change:** Any metric contained in a `sec_*` file, plus its S&P variant (`sec_*SP`).
* **Workflow:**
  1. **Step 1 – Pick Field & Dates**  
     A compact modal asks for the field (Spread, Duration, …, SpreadSP, etc.) and the date range.  The date inputs default to *exactly* the first and last dates presently shown on the chart, making "whole-range" edits a one-click job.
  2. **Step 2 – Review & Edit**  
     A second modal lists every date in the range with its existing value.  Type directly into the *New&nbsp;Value* column to overwrite.  Leave a cell blank to keep the original.
  3. **Export CSV**  
     Click **Export** to download a fully-formed CSV named `override_<Field>_<ISIN>_<timestamp>.csv` containing rows: `Field, ISIN, Date, Value`.  Hand this straight to the upstream data team or drop it into the loader – no re-formatting required.

### Under the Hood
* **Live Data Fetch:** The modal pulls existing values through `/security/get_field_data`, re-using the same loader pipeline that powers all analytics to guarantee consistency.
* **YAML Alias Map:** A simple `config/field_aliases.yaml` translates friendly field names to underlying DB/file names (identity mapping today – ready for future mismatches).
* **No Database Writes:** The feature is intentionally read-only; it prepares the override file but doesn't mutate production data, ensuring a safe audit trail.

### Why This Matters
* **Speed:** Fix a handful of bad points in seconds, without Excel gymnastics or risking raw file edits.
* **Accuracy:** Uses the exact values the app sees, avoiding off-by-one row errors.
* **Auditability:** The generated file is self-describing and timestamped, perfect for ticket attachments or SFTP upload workflows.

---

## Security-Level Analysis

- **Security-Level Analysis:**
  - The Securities summary and details pages now include time-series charts for YTM and YTW (with S&P overlays), in addition to Duration, Spread, and Spread Duration. Data is loaded from `sec_YTM.csv`, `sec_YTMSP.csv`, `sec_YTW.csv`, and `sec_YTWSP.csv`.
  - These charts use an extended color palette for clear distinction.
  - Allows comparison of security-level data files (`sec_*.csv`) to identify discrepancies.
  - **Max/Min Value Breach:** Checks security-level data (`sec_*.csv`, including Spread, YTM, and YTW) against configurable maximum and minimum value thresholds defined in `config.py` (`MAXMIN_THRESHOLDS`). Default thresholds for YTM/YTW are 0% (min) and 100% (max).

---

## Views and Functionality

- **Data Issue Tracking Views:**
  - Provides links to close specific issues.
  - Includes a form to add new issues with fields for user, date, description, priority, and optional Jira link.
- **Max/Min Value Breach Views:**
  - **Dashboard (`/maxmin/dashboard`):** Displays a summary card for each data file configured for max/min checks. Each card shows the count of securities breaching the maximum and minimum thresholds.
  - **Details (`/maxmin/details/<file_name>/<breach_type>`):** Shows a detailed table of securities that breached either the maximum (`max`) or minimum (`min`) threshold for the specified file.

---

## Technical Details

- **Attribution Data Loading:**
  - Attribution dashboards (summary, security, radar, charts) now load data from per-fund files in the format `att_factors_<FUNDCODE>.csv` (e.g., `att_factors_IG01.csv`).
  - When a user selects a fund, the application loads the corresponding attribution file for that fund only.
  - If no file exists for the selected fund, a clear message is shown: "No attribution available."
  - This replaces the previous approach of loading all attribution data from a single `att_factors.csv` file.

---

## Security Details Page Enhancements

- The security details page now displays **all static columns from reference.csv** in a grouped, clearly labeled tile on the left side of the page.
- The layout uses a two-column design: static info on the left (Identifiers, Classification, Financials, etc.), and all time-series charts on the right, making full use of the screen width.
- **Exclusion status** (if the security is on the exclusion list) and **open data issues** (if any) are shown in bold red in the static tile, with all open issues listed.
- A **Bloomberg YAS link** is generated for each security using the 'BBG Ticker Yellow' field, and opens in a new tab. The link format is now configurable via the `BLOOMBERG_YAS_URL_FORMAT` variable in `config.py`, making it easy to change or reuse the link format elsewhere in the app.
- The security details page now includes a **Fund Holdings Over Time (Based on Chart Dates)** tile above the first chart in the right column. This tile:
  - Uses the same table structure and color scheme (green for held, red for not held) as the comparison details page.
  - Shows which funds held the security on each date shown in the chart x-axis, using data from `w_secs.csv`.
  - Is only displayed if both holdings data and chart dates are available for the security.
  - Provides a clear message if holdings data is missing or unavailable for the chart period.
  - This brings the security details page in line with the comparison details view for fund holdings visualization.

---

## Watchlist Feature

The Watchlist feature provides a centralized way to track, review, and manage securities of interest across the application. It is accessible from the main navigation and is designed for collaborative workflows and auditability.

### Key Capabilities
- **Add to Watchlist:**
  - Users can add any security to the global watchlist using a dedicated modal dialog.
  - The modal includes:
    - **Filter dropdowns** for Ticker and Security Sub Type, allowing users to quickly narrow down the list of available securities.
    - **Search input** for filtering by ISIN, security name, or ticker.
    - **Scrollable, filterable security list:** All available securities are shown in a scrollable list, with client-side filtering and selection. Only one security can be selected at a time.
    - **Reason field:** Users must provide a reason for adding the security to the watchlist.
    - **User selection:** The user adding the entry must be selected from a dropdown (populated from `users.csv`).
    - **Browser autofill/autocomplete is disabled** for all fields to ensure only the custom UI is used for selection and entry (no browser suggestions).
  - The modal is responsive and wide (max-width: 900px, min-width: 600px, width: 70vw) to accommodate the security list and filters.
- **Watchlist Table:**
  - Displays all active and cleared watchlist entries in a responsive, paginated table.
  - Columns include ISIN (clickable for details), Security Name, Reason, Date Added, Added By, Last Checked, Status, and (when toggled) Cleared By, Cleared Date, and Clear Reason.
  - **Cleared entries** are hidden by default but can be shown with a toggle. Cleared columns are only visible when this toggle is enabled.
  - **Clear action:** Active entries can be cleared (not deleted) via a modal, which records who cleared the entry and why.
- **Workflow:**
  1. Click "Add to Watchlist" to open the modal.
  2. Filter/search and select a security from the list.
  3. Enter a reason and select the user.
  4. Submit to add the entry. The entry appears in the table as "Active".
  5. To clear an entry, click "Clear" and fill out the required fields in the modal. The entry is marked as "Cleared" and hidden unless the toggle is enabled.
- **Technical Details:**
  - All watchlist data is stored in a CSV file for auditability.
  - The UI is implemented in `watchlist_page.html` with Bootstrap modals and custom JavaScript for filtering and selection.
  - The backend uses Flask Blueprints and pandas for data management.
  - The feature is fully integrated with the application's user management and security reference data.

### Why This Matters
- Provides a transparent, auditable workflow for tracking securities of interest.
- Supports collaboration and accountability by recording who added/cleared entries and why.
- Makes it easy to review, filter, and manage the watchlist, even as the number of entries grows.

---

## Inspect (Contribution Analysis) Feature

The Inspect feature provides a powerful, interactive workflow for root-cause analysis of changes in any time-series metric (e.g., Duration, Spread, YTM, Spread Duration, etc.) at the security level. It is available directly from each chart on the metric detail page.

### How It Works
- **Access:**
  - Each chart on the metric page (e.g., Duration, Spread, YTM, Spread Duration) includes an **Inspect** button.
  - Clicking this button opens a modal (sub-window) where the user can configure the analysis.

- **User Input:**
  1. **Date Range Selection:**
     - The user selects a date range (must be a subset of the chart's available dates).
  2. **Data Category:**
     - The user chooses between "Original" or "SP" (S&P) data sources.

- **Calculation Logic:**
  1. For the selected metric, fund, and data source, the app loads the relevant weights (from `w_secs.csv`) and metric values (from `sec_<metric>.csv` or `sp_sec_<metric>.csv`).
  2. **Daily Contribution:**
     - For each security and each day in the range, the daily contribution is calculated as:
       - `Contribution = Weight × MetricValue`
  3. **Baseline:**
     - The contribution for each security is also calculated for the day *before* the selected range (serves as the baseline).
  4. **Average Contribution:**
     - For each security, the average contribution over the selected range is computed (sum of daily contributions divided by the number of days).
  5. **Change Calculation:**
     - The difference between the average contribution (over the range) and the baseline (day before) is calculated for each security.
  6. **Ranking:**
     - Securities are ranked by this difference. The top 10 positive (contributors) and top 10 negative (detractors) are identified.

- **Results Display:**
  - After calculation, a new results page is shown:
    - **Top 10 Contributors** and **Top 10 Detractors** are listed in separate tables, with their ISIN, Security Name, baseline, average, and change values.
    - Alongside the tables, a **vertical bar chart** visually represents these top contributors (green bars) and detractors (red bars). The chart is sorted by contribution difference, showing the largest positive impact on the left down to the largest negative impact on the right.
    - Each security listed in the tables is linked to its details page for further investigation.
    - This combined view helps users quickly identify which securities are driving changes in the metric over the selected period.

- **Supported Analytics:**
  - The Inspect feature is available for all key analytics:
    - Duration
    - Spread
    - YTM
    - Spread Duration
    - (and any other metric with security-level data)

### Why This Matters
- **Root Cause Analysis:**
  - Enables users to quickly pinpoint which securities are responsible for changes in portfolio analytics.
- **Flexible Investigation:**
  - Users can select any date range and data source, making it easy to investigate anomalies or performance drivers.
- **Integrated Workflow:**
  - Directly accessible from each chart, with seamless navigation to security details for deeper analysis.

### Technical Details
- Implemented in `views/metric_views.py` via the `_calculate_contributions` function and related routes.
- Handles missing data, flexible date parsing, and robust error handling.
- Merges security names from `reference.csv` for user-friendly display.
- Results are rendered in a dedicated results page and also available as JSON for API use.

---

## Config-Driven Metric Details Pages (May 2025)

### Central Metric Mapping
- The application now uses a YAML config (`config/metric_file_map.yaml`) to map each metric to its four key files:
  - `ts_<Metric>.csv` (aggregate/original)
  - `sp_ts_<Metric>.csv` (aggregate/S&P)
  - `sec_<Metric>.csv` (security-level/original)
  - `sec_<Metric>SP.csv` (security-level/S&P)
- This config also provides display names and units, making it easy to add or update metrics.

### Generic Fund Metric Details Page
- For every metric, there is now a generic details page: `/fund/<metric_name>_details/<fund_code>`.
- This page shows, for the selected date:
  - The value for the previous day
  - The value for the selected day
  - The 1 Day Change (selected - previous)
- The table is sorted by the absolute value of the 1 Day Change (largest first), so you can quickly spot the biggest changes.
- There is a single date selector at the top (defaults to the most recent date).
- The S&P/original toggle is available for all metrics.
- The metric page now links directly to these details pages for both original and S&P data for each fund.

### Data File Requirements
- All security-level files (`sec_*.csv`) must include a `Funds` column for fund-level filtering to work.
- If this column is missing, the details page will show an error.

## Individual Security Attribution Time Series (NEW)

This feature provides a detailed, interactive time-series visualization of attribution factors (L1/L2) for a single security. It allows for side-by-side comparison of Portfolio and Benchmark data, as well as Original and S&P data sources, for both attribution factors and security spread.

### Access and Navigation

-   **URL:** Accessible at `/attribution/security/timeseries`.
-   **Entry Point:** Navigated to from the `/attribution/security` page (Attribution by Security Summary) by clicking on an ISIN in the table.
-   **Query Parameters:** Requires `fund` (fund code) and `isin` (security ISIN) as query parameters. An optional `factor` parameter can be used to pre-select an attribution factor on page load.
    -   Example: `/attribution/security/timeseries?fund=IG01&isin=XS1234567890&factor=L1%20Rates%20Total`

### Key UI Elements and Functionality

-   **Fund and ISIN Display:** Read-only fields showing the selected Fund and ISIN.
-   **Net/Abs Toggle:** A toggle switch to view attribution factor values as either Net or Absolute.
-   **Factor Filtering Dropdown:**
    -   Allows users to select a specific L1 or L2 attribution factor to visualize.
    -   L1 factors are listed first, followed by a visual separator, then L2 factors.
-   **Link to Security Details:** A direct link to the main security details page (`/security/details/<metric_name>/<security_id>`), defaulting to the "Spread" metric for the selected ISIN.
    -   Example link: `/security/details/Spread/XS1234567890`

### Charts

1.  **Attribution Factor Chart:**
    -   **Content:** Displays daily values and a cumulative line for the selected attribution factor.
    -   **Breakdowns:** Shows data for both **Portfolio** and **Benchmark**.
    -   **Data Sources:** For each of Portfolio and Benchmark, it visualizes both **Original** data and **S&P** data.
    -   **Chart Type:** Daily values are presented as a bar chart, and cumulative values as a line chart, overlaid.
    -   **Conditional Display:** If a security is not present in the Portfolio or Benchmark for the selected fund, or if data is missing for S&P/Original, the relevant chart components are omitted, or a "data not found" message is displayed.

2.  **Spread Chart:**
    -   **Content:** Displays the time series of the security's Spread.
    -   **Data Sources:** Shows both **Original Spread** (from `sec_Spread.csv`) and **S&P Spread** (from `sec_SpreadSP.csv`).
    -   **Chart Type:** Line chart.
    -   **Conditional Display:** If spread data (Original or S&P) is missing for the security, the corresponding line is omitted, or a "data not found" message is shown.

### Data Sources

-   **Attribution Factors:** Per-fund attribution files (`Data/att_factors_<FUNDCODE>.csv`). The ISIN is used to filter data for the specific security.
-   **Spread Data:** Security-level spread files: `Data/sec_Spread.csv` (for Original) and `Data/sec_SpreadSP.csv` (for S&P).

### Styling

-   The page adopts the Tailwind CSS styling consistent with other modern pages in the application, particularly resembling `templates/attribution_charts.html`.

### Use Cases

-   Deep dive into the attribution drivers for a specific security over time.
-   Compare a security's factor attribution in the portfolio versus its benchmark.
-   Analyze differences between Original and S&P calculated attribution and spread data for a security.
-   Investigate securities flagged on the `/attribution/security` summary page.
