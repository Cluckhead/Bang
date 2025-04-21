# Application Features

This document provides a more detailed overview of specific application features.

## Generic Data Comparison

This feature allows users to compare two related security-level datasets side-by-side. It's configured via the `COMPARISON_CONFIG` dictionary in `config.py`.

### Summary View (`/compare/<comparison_type>/summary`)

*   Displays a table summarizing comparison statistics for multiple securities.
*   Calculates metrics like Level Correlation, Change Correlation, Mean Absolute Difference, and Max Absolute Difference between the two datasets for each security.
*   Integrates with `w_secs.csv` to show the current held status (`is_held`).
*   Supports:
    *   Server-side **filtering** based on static security attributes (e.g., Currency, Type) and held status (toggle to show/hide sold securities).
    *   Server-side **sorting** by any column.
    *   Server-side **pagination** to handle large datasets.

### Detail View (`/compare/<comparison_type>/details/<security_id>`)

*   Provides an in-depth look at the comparison for a single security.
*   Displays an overlayed **time-series chart** showing the values from both datasets over time.
*   Shows detailed **comparison statistics** specific to that security.
*   Lists other relevant **static attributes** for the security.
*   **Fund Holdings Table:**
    *   Displays a table below the main chart showing which funds held the selected security over the specific date range covered by the chart.
    *   **Data Source:** Uses the `w_secs.csv` file, linking on the security identifier (typically ISIN).
    *   **Date Alignment:** The columns in the table correspond directly to the dates shown on the x-axis of the time-series chart above it.
    *   **Color Coding:**
        *   `Green`: Indicates the security was held by the fund on that specific date (value in `w_secs.csv` is numeric and > 0).
        *   `Red`: Indicates the security was *not* held by the fund on that date (value in `w_secs.csv` is non-numeric, blank, zero, or NaN).
    *   **Funds:** Rows represent the different fund codes (`Funds` column in `w_secs.csv`) found holding the security.

*   **Data Issue Tracking:** Log, view, and manage data issues via `/issues` (stored in `Data/data_issues.csv`) 
    *   Uses `Data/users.csv` to populate dropdowns for 'Raised By' and 'Closed By'.
    *   Includes an optional 'Jira Link' field (accepts text, including URLs without `http://`) for tracking external tickets.
    *   Provides 'All Funds' and 'No Funds' options in the fund selector.
    *   Added 'Rimes' as a potential data source.
*   **Weight Check:** Compare fund and benchmark weights via `/weights/check`

## Data Staleness Detection

This feature monitors and identifies stale data in security files, helping users maintain data quality and reliability.

### Core Functionality (`staleness_processing.py`)

* **File Processing:** Automatically processes files with naming pattern `sec_*.csv` and `sp_sec_*.csv` in the configured data folder.
* **Detection Methods:**
  * **Placeholder Pattern Detection:** Identifies consecutive placeholder values (default: repeated values of 100) that indicate stale or missing data.
  * **Time-based Staleness:** Flags securities where the last valid update is older than a configurable threshold (default: 5 days).
* **Customizable Configuration:**
  * Configurable placeholder values that indicate stale data
  * Adjustable threshold for consecutive placeholders (default: 3)
  * Configurable day threshold for time-based staleness (default: 5 days)
* **Exclusion Support:** Ability to exclude specific securities from staleness analysis

### Summary View (`/staleness/summary`)

* Displays a table summarizing staleness statistics across all processed files
* Shows metrics including:
  * Latest date in each file
  * Total securities count
  * Count and percentage of stale securities
  * Quick access to detailed views

### Detail View (`/staleness/details/<file_name>`)

* Provides an in-depth look at stale securities in a specific file
* Lists each stale security with:
  * Security ID and metadata (Name, Type, Currency, etc.)
  * Last update date
  * Days stale
  * Staleness type (placeholder pattern or time-based)
  * Number of consecutive placeholders (if applicable)
