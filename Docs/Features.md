# Application Features

## Table of Contents
- [Date Parsing Flexibility](#date-parsing-flexibility)
- [File Audit & Consistency Checker (NEW)](#file-audit--consistency-checker-new)
- [Generic Data Comparison](#generic-data-comparison)
- [Data Staleness Detection](#data-staleness-detection)
- [Security-Level Analysis: Min=0 Exclusion Toggle](#security-level-analysis-min0-exclusion-toggle)
- [Security-Level Analysis](#security-level-analysis)
- [Views and Functionality](#views-and-functionality)
- [Technical Details](#technical-details)
- [Security Details Page Enhancements](#security-details-page-enhancements)
- [Watchlist Feature](#watchlist-feature)
- [Inspect (Contribution Analysis) Feature](#inspect-contribution-analysis-feature)
- [Attribution Data API (NEW)](#attribution-data-api-new)

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
