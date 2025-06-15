1. Make Jira Links in the Issue Tracker Clickable
Change: On the "Issue Tracking" page, Jira links that are not full URLs (e.g., just an issue key like PROJ-123) should be automatically converted into clickable hyperlinks that point to the correct location in Jira.
Outcome: Users can navigate directly from the Data Checker to their external issue tracking system with a single click, saving the time and effort of manually copying and pasting the issue key.
Why it's better: This streamlines the workflow for analysts who need to cross-reference data issues with tickets in other systems, making the integration between tools feel seamless.
Files Involved: views/issue_views.py (to prepend a base Jira URL to the link if it's not a full URL already) and templates/issues_page.html (to ensure the link is rendered as an <a> tag). 

2. Live Search in "Add to Watchlist" Modal
Change: In the "Add to Watchlist" modal, the search box for securities should filter the list below it in real-time as the user types, rather than requiring an exact search.
Outcome: Users can find the security they are looking for much faster, even if they only know part of its name or ISIN. The list would dynamically shrink to show only matching results.
Why it's better: This replaces a static dropdown with a modern, interactive search experience. It dramatically reduces the time spent scrolling through a potentially long list, making the feature quicker and more intuitive to use.
Files Involved: templates/watchlist_page.html (to add the JavaScript logic for real-time filtering) and static/js/main.js (if the logic is centralized). 

3. Add Confirmation for Destructive Actions
Change: On the "Get Data" and "Get Attribution Data" pages, show a simple confirmation dialog (e.g., "Are you sure you want to overwrite this data?") when a user clicks a button that will overwrite or "redo" a file. 

Outcome: Users are given a chance to cancel an action that could lead to accidental data loss.
Why it's better: This is a standard safety pattern for any destructive action in a user interface. It prevents costly mistakes from a single misclick, improving user confidence and data safety.
Files Involved: templates/get_data.html and templates/get_attribution_data.html (to add JavaScript for the confirmation prompt).

4. Highlight the Active Page in the Navigation Sidebar
Change: In the main navigation sidebar, the link corresponding to the page the user is currently viewing should be visually highlighted (e.g., with a different background color or bolder text).
Outcome: Users have a clear visual cue of their current location within the application's structure.
Why it's better: This is a fundamental aspect of good navigation design. It helps users orient themselves, understand the application's layout, and navigate more confidently without getting lost.
Files Involved: templates/base.html (to add logic comparing request.endpoint to the navigation item's endpoint) and static/css/tailwind.output.css (to add the styling for the active state).

5. Provide Visual Cues for Clickable Chart Points
Change: On the security details page charts, change the mouse cursor to a pointer (the "hand" icon) when hovering over a data point to indicate that it is clickable for the "Mark Good" feature. 
Outcome: Users will be more likely to discover the "Mark Good" functionality organically.
Why it's better: This improves the discoverability of a powerful feature without cluttering the UI. The visual feedback makes the charts feel more interactive and hints at hidden capabilities.
Files Involved: templates/security_details_page.html (to add the onHover configuration to the Chart.js options).

6. Make the "Show Cleared" Toggle More Obvious on the Watchlist
Change: When the "Show Cleared Entries" toggle is checked on the Watchlist page, not only should the cleared rows appear, but the hidden "Cleared By", "Cleared Date", and "Clear Reason" columns should also become visible in the table. 
Outcome: The UI becomes cleaner by default, hiding irrelevant columns. When a user explicitly asks to see cleared items, they are presented with all the relevant context for why those items were cleared.
Why it's better: This creates a cleaner and more context-aware interface. It hides complexity until it's needed, reducing cognitive load for the most common use case (viewing active items).
Files Involved: templates/watchlist_page.html (to add JavaScript that toggles the visibility of both the rows and the specific columns).

7. Indicate When Filters Are "Dirty"
Change: On pages with filter forms and an "Apply" button (like the Comparison Summary), provide a subtle visual cue (e.g., the "Apply" button changes color) after a user changes a filter but before they have clicked "Apply". The cue should disappear after the form is submitted.
Outcome: The user is made aware that the data currently displayed does not reflect their most recent filter selection.
Why it's better: This prevents confusion where a user might think the data has updated automatically. It clarifies the state of the application, showing that the controls and the data view are temporarily out of sync.
Files Involved: templates/comparison_summary_base.html and templates/securities_page.html (to add JavaScript listeners to the form inputs).

8. Improve Feedback on Missing Data Files
Change: When a data file required for a page (e.g., ts_spread.csv for the Spread Analysis page) is missing entirely, display a prominent, user-friendly error message that explicitly names the missing file.
Outcome: A user or administrator immediately knows the root cause of the empty page and which specific file needs to be placed in the Data directory.
Why it's better: This provides direct, actionable feedback instead of a generic "An error occurred" or a confusing empty state, significantly speeding up troubleshooting of data pipeline issues.
Files Involved: views/metric_views.py, views/security_views.py, and other view files that load data (to add the file existence check and pass a specific message to the template).

9. Attribution Summary Tables
Change: On the "Attribution Residuals Summary" page, make all data columns in both the "Benchmark Attribution" and "Portfolio Attribution" tables clickable for sorting. This includes columns for Date, Fund, and all L0, L1, or L2 factor values.
Outcome: Users can dynamically re-order the results to quickly find the dates or funds with the highest/lowest residuals, or the largest contributions from specific factors like "L1 Credit" or "L1 Rates".
Why it's better: The current view is static and sorted only by date. Allowing users to sort by any metric enables them to perform on-the-fly analysis to pinpoint the most significant attribution events or funds without having to export the data.
Files Involved: templates/attribution_summary.html (to add the sortable class and necessary attributes to table headers) and static/js/main.js (to initialize the table sorter for these new tables).



10. Dashboard Z-Score Summary Table
Change: Make every column header in the "Latest Change Z-Score Summary" table on the main dashboard clickable for sorting.
Outcome: Users can immediately sort the entire dashboard view by the metric they are most interested in (e.g., find the fund with the highest "Spread - Z-Score" across all metrics).
Why it's better: The dashboard's purpose is to provide a high-level overview of the most significant changes. Adding sorting capability makes this overview interactive and allows each user to tailor the summary to their specific area of focus, enhancing its analytical value.
Files Involved: templates/index.html (to add sortable classes to the table headers) and static/js/main.js (to initialize the sorter on the dashboard table).


11. Staleness and Max/Min Breach Details Tables
Change: On the "Stale Data Details" and "Max/Min Breach Details" pages, make the data columns sortable. Key columns would be "Days Stale" or "Days Breaching", respectively, as well as any static columns like "Security Name" or "Currency".
Outcome: When investigating data quality issues, users can sort the list of problematic securities to prioritize the ones that have been stale the longest or have breached thresholds most frequently.
Why it's better: This allows users to triage data quality problems more effectively. Sorting by the severity or duration of the issue helps focus attention where it's most needed.
Files Involved: templates/staleness_details.html, templates/maxmin_details.html, and static/js/main.js.

12. Attribution by Security Table
Change: Replace the existing custom sorting JavaScript on the "Attribution Security-Level Check" page with the standardized, more robust tableSorter.js module used elsewhere in the application.
Outcome: Sorting behavior becomes consistent with the rest of the application. The tableSorter.js module is better at handling numeric vs. text sorting, ensuring that values like "Returns" and "Residual Diff" sort correctly as numbers.
Why it's better: This improves both the user experience (with more accurate sorting) and code maintainability by removing redundant, custom JavaScript and relying on a single, centralized sorting utility.
Files Involved: templates/attribution_security_page.html (to remove old script and add standard sortable classes to headers) and static/js/main.js (to initialize the sorter for this table).

