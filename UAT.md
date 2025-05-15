# User Acceptance Testing Checklist

This document provides a comprehensive checklist for testing all features and pages of the Simple Data Checker application.

## Dashboard and Navigation

- [ ] Main dashboard displays correctly (`/`, `index.html`)
- [ ] Navigation sidebar contains all expected links
- [ ] Z-Score summary table displays on dashboard
- [ ] Metric links navigate to correct pages
- [ ] Error page displays appropriately when needed (`error.html`)

## Time-Series Metric Analysis

- [ ] Metric detail page loads successfully (`/metric/<metric_name>`, `metric_page_js.html`)
- [ ] Toggle switch for SP data works correctly
- [ ] Chart.js charts display time-series data properly
- [ ] Filters drawer functions as expected
- [ ] Fund Group filtering works as expected
- [ ] Date range selection functions correctly
- [ ] Chart data updates when filters are applied
- [ ] Inspect (Contribution Analysis) button opens the modal
- [ ] Inspect date range selection works properly
- [ ] Inspect results page displays contributors and detractors correctly (`inspect_results.html`)

## Security-Level Analysis

- [ ] Securities summary page loads successfully (`/security/summary`, `securities_page.html`)
- [ ] Filter/search form functions correctly
- [ ] "Exclude securities where Min = 0" toggle works as expected
- [ ] Pagination controls function correctly
- [ ] Sorting by columns works as expected
- [ ] CSV download option works correctly
- [ ] Security details page loads successfully (`/security/details/<metric_name>/<security_id>`, `security_details_page.html`)
- [ ] All static columns from reference.csv display in the grouped tile
- [ ] All charts (Value, Price, Duration, YTM, YTW, Spread) display correctly
- [ ] Exclusion status displays in bold red when applicable
- [ ] Open data issues display when applicable
- [ ] Bloomberg YAS link generates correctly and opens in a new tab
- [ ] Fund Holdings Over Time tile displays correctly

## Generic Data Comparison

- [ ] Comparison summary page loads for all types (`/compare/<comparison_type>/summary`, `comparison_summary_base.html`)
- [ ] Server-side filtering works correctly for all attributes
- [ ] Server-side sorting functions as expected
- [ ] Server-side pagination works properly
- [ ] Held status toggle (show/hide sold securities) functions correctly
- [ ] Fund Group filtering works as expected
- [ ] Comparison details page loads correctly (`/compare/<comparison_type>/details/<security_id>`, `comparison_details_base.html`)
- [ ] Time-series chart shows values from both datasets
- [ ] Comparison statistics display correctly
- [ ] Static attributes list displays properly
- [ ] Fund Holdings Table shows correct data with proper color coding

## Fund-Specific Views

- [ ] Fund overview page loads correctly (`/fund/<fund_code>`, `fund_detail_page.html`)
- [ ] Multiple charts with SP data toggle display and function properly
- [ ] Fund duration details page loads correctly (`/fund/duration_details/<fund_code>`, `fund_duration_details.html`)
- [ ] Security duration changes table displays correctly
- [ ] Generic fund metric details page loads correctly (`/fund/<metric_name>_details/<fund_code>`, `fund_metric_details.html`)
- [ ] Previous day value, selected day value, and 1 Day Change display correctly
- [ ] Table sorts by absolute value of 1 Day Change
- [ ] Date selector functions correctly
- [ ] S&P/original toggle works properly

## Security Exclusions

- [ ] Exclusions page loads correctly (`/exclusions`, `exclusions_page.html`)
- [ ] Current exclusions display properly
- [ ] Add exclusion form functions correctly
- [ ] Remove exclusion functionality works as expected

## Data Issue Tracking

- [ ] Issues page loads correctly (`/issues`, `issues_page.html`)
- [ ] Current issues display properly
- [ ] Add issue form with user dropdown functions correctly
- [ ] Close issue functionality works as expected
- [ ] Jira link field accepts input correctly
- [ ] All Funds and No Funds options work in the fund selector

## Weight Check

- [ ] Weight check page loads correctly (`/weights/check`, `weight_check_page.html`)
- [ ] Fund and benchmark weights compare correctly
- [ ] Case-insensitive weight file detection works properly

## Yield Curve Analysis

- [ ] Curve summary page loads correctly (`/curve/summary`, `curve_summary.html`)
- [ ] Inconsistency check table displays properly
- [ ] Curve details page loads correctly (`/curve/details/<currency>`, `curve_details.html`)
- [ ] Chart.js line chart displays properly
- [ ] Date selector functions correctly

## Attribution Analysis

- [ ] Attribution summary page loads correctly (`/attribution`, `attribution_summary.html`)
- [ ] 3-way toggle (L0/L1/L2) functions properly
- [ ] Comparison data displays correctly
- [ ] Attribution by Security summary page loads correctly (`/attribution/security`, `attribution_security_page.html`)
- [ ] Table of securities with L0/L1/L2 factors displays correctly
- [ ] Links to time series view function properly
- [ ] Individual Security Attribution Time Series page loads correctly (`/attribution/security/timeseries`, `attribution_security_timeseries.html`)
- [ ] Charts for L1/L2 factors over time display correctly
- [ ] Portfolio/Benchmark data displays correctly
- [ ] Original/S&P data displays correctly
- [ ] Spread chart displays correctly
- [ ] Factor selection dropdown functions properly
- [ ] Net/Abs toggle works as expected
- [ ] Attribution Factor Charts page loads correctly (`/attribution/charts`, `attribution_charts.html`)
- [ ] Detailed charts for selected L1/L2 factors display correctly
- [ ] Attribution radar chart loads correctly (`/attribution/radar`, `attribution_radar.html`)
- [ ] Radar visualization displays properly

## Max/Min Value Breach

- [ ] Max/Min dashboard loads correctly (`/maxmin/dashboard`, `maxmin_dashboard.html`)
- [ ] Summary cards for each data file display properly
- [ ] Max/Min details page loads correctly (`/maxmin/details/<file_name>/<breach_type>`, `maxmin_details.html`)
- [ ] Table of breaching securities displays correctly

## Watchlist Management

- [ ] Watchlist page loads correctly (`/watchlist`, `watchlist_page.html`)
- [ ] Add to Watchlist modal functions properly
- [ ] Filter dropdowns for Ticker and Security Sub Type work correctly
- [ ] Search input filters by ISIN, security name, or ticker
- [ ] Scrollable, filterable security list displays properly
- [ ] Reason field accepts input correctly
- [ ] User selection dropdown functions properly
- [ ] Browser autofill/autocomplete is disabled for all fields
- [ ] Watchlist table displays all active and cleared entries correctly
- [ ] Cleared entries toggle works as expected
- [ ] Clear action modal functions properly

## Data Staleness Detection

- [ ] Staleness summary page loads correctly (`/staleness/summary`, `staleness_dashboard.html`)
- [ ] Table summarizing staleness statistics displays properly
- [ ] Staleness details page loads correctly (`/staleness/details/<file_name>`, `staleness_details.html`)
- [ ] Table of stale securities displays correctly

## Data API and Simulation

- [ ] API simulation page loads correctly (`/get_data`, `get_data.html`)
- [ ] Data status displays properly
- [ ] Fund selection functions correctly
- [ ] Date inputs work as expected
- [ ] Run Data Consistency Audit button functions properly
- [ ] File Audit feature displays comprehensive report
- [ ] Attribution Data API page loads correctly (`/api/get_attribution_data`, `get_attribution_data.html`)
- [ ] Status table for attribution files displays correctly
- [ ] Fund selection with group support functions properly
- [ ] Date range selection works correctly
- [ ] Write mode selection (append or redo/overwrite) functions properly
- [ ] API call logic executes correctly for each selected fund
- [ ] Status feedback displays after processing

## Preprocessing and Utilities

- [ ] Date parsing flexibility works correctly for all formats
- [ ] Preprocessing handles date header replacement properly
- [ ] Data type conversion functions correctly
- [ ] Aggregation/pivoting works as expected
- [ ] Output generation saves processed data in standardized formats

## Data File Integrity

- [ ] All time-series files (`ts_*.csv`) load correctly
- [ ] All security-level files (`sec_*.csv`) load correctly
- [ ] All weight files (`w_*.csv`) load correctly
- [ ] Curves file (`curves.csv`) loads correctly
- [ ] Attribution files (`att_factors_<FUNDCODE>.csv`) load correctly
- [ ] Users file (`users.csv`) loads correctly
- [ ] Issues file (`data_issues.csv`) loads correctly
- [ ] Exclusions file (`exclusions.csv`) loads correctly 