// This file acts as the main entry point for the application's JavaScript.
// It runs after the DOM is fully loaded and performs several key initializations:
// 1. Imports necessary functions from UI modules (chart rendering, table filtering).
// 2. Checks for the presence of specific elements on the page to determine the context
//    (e.g., metric details page, securities list page, single security detail page).
// 3. If on a metric details page (`metric_page_js.html`):
//    - Finds the embedded JSON data (`<script id="chartData">`).
//    - Parses the JSON data containing historical values and calculated metrics for all funds.
//    - Calls `renderChartsAndTables` from `chartRenderer.js` to dynamically create
//      the metric tables and time-series charts for each fund code.
// 4. If on a securities list page (`securities_page.html`):
//    - Finds the main securities table (`<table id="securities-table">`).
//    - Calls `initSecurityTableFilter` from `securityTableFilter.js` to add
//      interactive filtering capabilities to the table header.
// 5. If on a single security detail page (`security_details_page.html`):
//    - Finds the chart canvas (`<canvas id="securityChart">`) and its associated JSON data (`<script id="chartJsonData">`).
//    - Parses the JSON data containing the time-series for that specific security.
//    - Calls `renderSingleSecurityChart` from `chartRenderer.js` to display the chart.
// This modular approach ensures that initialization code only runs when the corresponding HTML elements are present.

// static/js/main.js
// Purpose: Main entry point for client-side JavaScript. Initializes modules based on page content.

import { renderChartsAndTables, renderSingleSecurityChart, renderFundCharts, toggleSecondaryDataVisibility } from './modules/ui/chartRenderer.js';
import { initSecurityTableFilter } from './modules/ui/securityTableFilter.js';
import { initTableSorter } from './modules/ui/tableSorter.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // --- Sidebar Toggle Logic ---
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    const breadcrumbsContainer = document.getElementById('breadcrumbs-container');
    const toggleButton = document.getElementById('sidebar-toggle-btn');
    const body = document.body;
    const SIDEBAR_COLLAPSED_KEY = 'sidebarCollapsed';

    // Function to apply state based on class
    const applySidebarState = (isCollapsed) => {
        if (isCollapsed) {
            sidebar.classList.remove('w-[220px]');
            sidebar.classList.add('w-16');
            mainContent.classList.remove('ml-[220px]');
            mainContent.classList.add('ml-16');
            if (breadcrumbsContainer) {
                 breadcrumbsContainer.classList.remove('ml-[220px]');
                 breadcrumbsContainer.classList.add('ml-16');
            }
            // Hide text elements within the sidebar
            sidebar.querySelectorAll('.nav-text').forEach(el => el.classList.add('hidden'));
            // Adjust padding if necessary when collapsed
            sidebar.classList.remove('p-4');
            sidebar.classList.add('p-2'); 
        } else {
            sidebar.classList.remove('w-16');
            sidebar.classList.add('w-[220px]');
            mainContent.classList.remove('ml-16');
            mainContent.classList.add('ml-[220px]');
             if (breadcrumbsContainer) {
                 breadcrumbsContainer.classList.remove('ml-16');
                 breadcrumbsContainer.classList.add('ml-[220px]');
             }
            // Show text elements
            sidebar.querySelectorAll('.nav-text').forEach(el => el.classList.remove('hidden'));
            // Restore padding
            sidebar.classList.remove('p-2');
            sidebar.classList.add('p-4');
        }
    };

    // Check localStorage for saved state
    const isInitiallyCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
    if (isInitiallyCollapsed) {
        body.classList.add('sidebar-collapsed');
        applySidebarState(true);
    } else {
        applySidebarState(false); // Apply default expanded state
    }

    // Add toggle button listener
    if (toggleButton && sidebar && mainContent) {
        toggleButton.addEventListener('click', () => {
            const isCollapsed = body.classList.toggle('sidebar-collapsed');
            applySidebarState(isCollapsed);
            // Save state to localStorage
            localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isCollapsed);
        });
    } else {
        console.warn("Sidebar toggle button, sidebar, or main content element not found.");
    }
    // --- End Sidebar Toggle Logic ---

    // --- Shared Elements ---
    const spComparisonToggle = document.getElementById('toggleSpData'); // Existing toggle for S&P *comparison*
    const spValidToggle = document.getElementById('toggleSpValid'); // NEW toggle for S&P *valid* filter

    // --- Metric Page Specific Logic ---
    const metricChartDataElement = document.getElementById('chartData');
    const metricChartsArea = document.getElementById('chartsArea');

    if (metricChartDataElement && metricChartsArea) {
        console.log("Metric page detected. Initializing charts and toggles.");

        // --- NEW: S&P Valid Filter Toggle Logic ---
        if (spValidToggle) {
            console.log("[main.js] Attaching toggle listener for S&P Valid Filter.");
            spValidToggle.addEventListener('change', (event) => {
                const isChecked = event.target.checked;
                console.log(`[main.js Metric Page Toggle] S&P Valid toggle changed. Is Checked: ${isChecked}`);

                // Construct the new URL
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('sp_valid', isChecked ? 'true' : 'false');

                // Reload the page with the new query parameter
                console.log(`Reloading to: ${currentUrl.toString()}`);
                window.location.href = currentUrl.toString();
            });
        } else {
             console.log("[main.js] S&P Valid toggle switch (#toggleSpValid) not found for Metric Page.");
        }
        // --- END: S&P Valid Filter Toggle Logic ---

        try {
            const chartDataJson = metricChartDataElement.textContent;
            console.log("Raw JSON string from script tag:", chartDataJson);
            const fullChartData = JSON.parse(chartDataJson);
            console.log('Parsed fullChartData object:', fullChartData);
            const metadata = fullChartData ? fullChartData.metadata : null; 
            console.log('Checking fullChartData.metadata:', metadata);
            console.log('Checking fullChartData.funds:', fullChartData ? fullChartData.funds : 'fullChartData is null/undefined');

            if (metadata && fullChartData.funds && Object.keys(fullChartData.funds).length > 0) {
                console.log("Conditional check passed. Calling renderChartsAndTables...");
                let showSecondary = true;
                if (spComparisonToggle) {
                    showSecondary = spComparisonToggle.checked;
                }
                renderChartsAndTables(
                    metricChartsArea,
                    fullChartData,
                    showSecondary
                );

                // Now, attach the event listener if the toggle exists and data is available
                if (spComparisonToggle && metadata.secondary_data_available) {
                    console.log("[main.js] Attaching toggle listener for S&P Comparison Data on Metric Page.");
                    spComparisonToggle.disabled = false;
                    // Show the comparison toggle container
                    const spToggleContainer = document.getElementById('sp-toggle-container');
                    if (spToggleContainer) spToggleContainer.style.display = 'block';

                    spComparisonToggle.addEventListener('change', (event) => {
                        const showSecondary = event.target.checked;
                        console.log(`[main.js Metric Page Toggle] S&P Comparison toggle changed. Show Secondary: ${showSecondary}`);
                        renderChartsAndTables(
                            metricChartsArea,
                            fullChartData,
                            showSecondary
                        );
                    });
                } else if (spComparisonToggle) {
                     console.log("[main.js] S&P Comparison toggle exists, but secondary data not available for Metric Page.");
                     spComparisonToggle.disabled = true;
                     const spToggleContainer = document.getElementById('sp-toggle-container');
                      if (spToggleContainer) spToggleContainer.style.display = 'block'; // Still show, but disabled
                      // Optionally update label
                      const label = spToggleContainer.querySelector('label');
                      if (label) label.textContent += ' (N/A)';
                } else {
                    console.log("[main.js] S&P Comparison toggle switch (#toggleSpData) not found for Metric Page.");
                }

                // --- START: Inspect Modal Logic (MOVED INSIDE TRY BLOCK) ---
                function addInspectButtonsToCharts(chartDataForButtons) { // Use parameter
                    if (!chartDataForButtons || !chartDataForButtons.funds) return;
                    Object.keys(chartDataForButtons.funds).forEach(fundCode => {
                        const card = document.getElementById(`fund-card-${fundCode}`); // Assumes chartRenderer creates this ID
                        if (!card) {
                           console.warn(`[Inspect Logic] Card container 'fund-card-${fundCode}' not found. Cannot add Inspect button.`);
                           return;
                        }
                        // Check if button already exists to prevent duplicates on re-render
                        if (card.querySelector('.inspect-btn')) return; 
                        
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'inspect-btn px-3 py-1 rounded-md bg-secondary text-white hover:bg-secondary-dark text-sm mt-2 absolute top-1 right-1 z-10'; // Added positioning and z-index
                        btn.textContent = 'Inspect';
                        btn.dataset.fund = fundCode;
                        btn.dataset.metric = chartDataForButtons.metadata?.metric_name || '';
                        
                        // Gather dates robustly
                        let allDates = [];
                        (chartDataForButtons.funds[fundCode]?.charts || []).forEach(chartConfig => {
                            if (Array.isArray(chartConfig.labels)) {
                                allDates = allDates.concat(chartConfig.labels);
                            }
                        });
                        allDates = Array.from(new Set(allDates)).sort();
                        btn.dataset.minDate = allDates[0] || '';
                        btn.dataset.maxDate = allDates[allDates.length - 1] || '';
                        
                        console.log(`[main.js] Adding Inspect button for ${fundCode}. Min: ${btn.dataset.minDate}, Max: ${btn.dataset.maxDate}.`); // DEBUG
                        btn.addEventListener('click', openInspectModalFromButton); // Attach listener
                        card.appendChild(btn);
                    });
                }

                // Initial call to add buttons after first render
                addInspectButtonsToCharts(fullChartData);
                
                // Ensure buttons are re-added if charts re-render (e.g., SP toggle)
                 const origRenderChartsAndTables = window.renderChartsAndTables; // Get potentially patched version
                 window.renderChartsAndTables = function(...args) {
                     origRenderChartsAndTables.apply(this, args);
                     addInspectButtonsToCharts(args[1]); // args[1] is fullChartData
                 };

                // Modal elements and open/close/submit logic
                const inspectModal = document.getElementById('inspectModal');
                const closeInspectModalBtn = document.getElementById('closeInspectModal');
                const cancelInspectModalBtn = document.getElementById('cancelInspectModal');
                const inspectForm = document.getElementById('inspectForm');
                const runAnalysisBtn = document.getElementById('runAnalysisBtn');

                function openInspectModalFromButton(e) {
                    console.log('[main.js] openInspectModalFromButton triggered!'); // DEBUG
                    const btn = e.currentTarget;
                    console.log('[main.js] Button clicked:', btn); // DEBUG
                    document.getElementById('inspectFund').value = btn.dataset.fund;
                    document.getElementById('inspectMetric').value = btn.dataset.metric;
                    document.getElementById('inspectStartDate').min = btn.dataset.minDate;
                    document.getElementById('inspectStartDate').max = btn.dataset.maxDate;
                    document.getElementById('inspectEndDate').min = btn.dataset.minDate;
                    document.getElementById('inspectEndDate').max = btn.dataset.maxDate;
                    document.getElementById('inspectStartDate').value = btn.dataset.minDate;
                    document.getElementById('inspectEndDate').value = btn.dataset.maxDate;
                    // Ensure form action is set if needed (though we redirect directly now)
                    // inspectForm.action = `/metric/${btn.dataset.metric}/inspect`; 
                    inspectModal.classList.remove('hidden');
                }

                function closeInspectModal() {
                    inspectModal.classList.add('hidden');
                }

                // Attach listeners ONLY if elements exist
                if (closeInspectModalBtn) closeInspectModalBtn.addEventListener('click', closeInspectModal);
                if (cancelInspectModalBtn) cancelInspectModalBtn.addEventListener('click', closeInspectModal);
                if (inspectModal) inspectModal.addEventListener('click', (e) => {
                    if (e.target === inspectModal) closeInspectModal();
                });

                if (runAnalysisBtn) runAnalysisBtn.addEventListener('click', function() {
                    console.log('[Inspect Modal] Run Analysis button clicked'); // DEBUG
                    const fund_code = document.getElementById('inspectFund').value;
                    const metric_name = document.getElementById('inspectMetric').value;
                    const start_date = document.getElementById('inspectStartDate').value;
                    const end_date = document.getElementById('inspectEndDate').value;
                    const dataSourceRadio = inspectForm.querySelector('input[name="data_source"]:checked');
                    const data_source = dataSourceRadio ? dataSourceRadio.value : 'Original'; 
                    if (start_date > end_date) {
                        alert('Start date must be before or equal to end date.');
                        return;
                    }
                    const resultsUrl = `/metric/inspect/results?metric_name=${encodeURIComponent(metric_name)}&fund_code=${encodeURIComponent(fund_code)}&start_date=${encodeURIComponent(start_date)}&end_date=${encodeURIComponent(end_date)}&data_source=${encodeURIComponent(data_source)}`;
                    console.log('[Inspect Modal] Redirecting to:', resultsUrl);
                    window.location.href = resultsUrl;
                });
                // --- END Inspect Modal Logic ---

            } else {
                console.error('Parsed metric chart data is missing expected structure or funds are empty:', fullChartData);
                metricChartsArea.innerHTML = '<div class="alert alert-danger">Error: Invalid data structure or no fund data.</div>';
            }
        } catch (e) {
            console.error('Error processing metric chart data:', e);
            metricChartsArea.innerHTML = '<div class="alert alert-danger">Error loading chart data. Check console.</div>';
        }
    }

    // --- Fund Detail Page Logic --- 
    const fundChartDataElement = document.getElementById('fundChartData');
    const fundChartsArea = document.getElementById('fundChartsArea');

    if (fundChartDataElement && fundChartsArea) {
        console.log("Fund detail page detected. Initializing charts.");

        // --- NEW: S&P Valid Filter Toggle Logic for Fund Detail Page ---
        if (spValidToggle) {
            console.log("[main.js] Attaching toggle listener for S&P Valid Filter on Fund Detail Page.");
            spValidToggle.addEventListener('change', (event) => {
                const isChecked = event.target.checked;
                console.log(`[main.js Fund Detail Page Toggle] S&P Valid toggle changed. Is Checked: ${isChecked}`);

                // Construct the new URL
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('sp_valid', isChecked ? 'true' : 'false');

                // Reload the page with the new query parameter
                console.log(`Reloading to: ${currentUrl.toString()}`);
                window.location.href = currentUrl.toString();
            });
        } else {
            console.log("[main.js] S&P Valid toggle switch (#toggleSpValid) not found for Fund Detail Page.");
        }
        // --- END: S&P Valid Filter Toggle Logic for Fund Detail Page ---

        try {
            const fundChartDataJson = fundChartDataElement.textContent;
            const allChartData = JSON.parse(fundChartDataJson);
            console.log('Parsed fund chart data:', JSON.parse(JSON.stringify(allChartData)));

            // Check if any SP data is available *before* rendering
            const anySpDataAvailable = allChartData.some(chartInfo => 
                chartInfo.datasets && chartInfo.datasets.some(ds => ds.isSpData === true)
            );

            if (Array.isArray(allChartData)) { // Check if it's an array (even if empty)
                // Render charts first
                 renderFundCharts(fundChartsArea, allChartData);

                // Setup toggle based on data availability
                 if (spComparisonToggle) { // Use the correct variable name
                    if (anySpDataAvailable) {
                         console.log("[main.js] Attaching toggle listener for S&P Comparison Data on Fund Detail Page.");
                        spComparisonToggle.disabled = false;
                          // Show the comparison toggle container
                          const spToggleContainer = document.getElementById('sp-toggle-container');
                          if (spToggleContainer) spToggleContainer.style.display = 'block';
                          // Ensure label is correct
                         const label = spToggleContainer.querySelector('label');
                         if (label) label.textContent = 'Show SP Comparison Data';

                        spComparisonToggle.addEventListener('change', (event) => {
                            const showSecondary = event.target.checked;
                            console.log(`[main.js Fund Detail Page Toggle] Toggle changed. Show SP: ${showSecondary}`);
                            toggleSecondaryDataVisibility(showSecondary); // Call imported function
                        });
                    } else {
                        console.log("[main.js] Fund Detail Page: No SP data available, disabling SP comparison toggle.");
                        spComparisonToggle.disabled = true;
                        spComparisonToggle.checked = false;
                         // Show the comparison toggle container but disabled
                         const spToggleContainer = document.getElementById('sp-toggle-container');
                         if (spToggleContainer) spToggleContainer.style.display = 'block';
                         // Update label
                         const label = spToggleContainer.querySelector('label');
                         if (label) label.textContent = 'Show SP Comparison Data (N/A)';
                    }
                } else {
                    console.log("[main.js] S&P Comparison toggle switch (#toggleSpData) not found for Fund Detail Page.");
                }
            } else {
                 console.error('Parsed fund chart data is not an array or is invalid:', allChartData);
                fundChartsArea.innerHTML = '<div class="alert alert-danger">Error: Invalid chart data received.</div>';
            }
        } catch (e) {
            console.error('Error processing fund chart data:', e);
            fundChartsArea.innerHTML = '<div class="alert alert-danger">Error loading fund charts. Check console.</div>';
        }
    }


    // --- Securities Summary Page (Filterable & Sortable Table) ---
    const securitiesTable = document.getElementById('securities-table');
    if (securitiesTable) {
        console.log("Securities page table detected. Initializing client-side sorter (filtering is server-side).");
        // initSecurityTableFilter('securities-table'); // REMOVED: Filtering is now server-side
        initTableSorter('securities-table'); // Keep client-side sorting for instant feedback after load
    } else {
        // console.log("Securities table not found, skipping table features initialization.");
    }

    // --- Comparison Summary Page (Filterable & Sortable Table) ---
    const comparisonTable = document.getElementById('comparison-table');
    if (comparisonTable) {
        console.log("Comparison page table detected. Initializing sorter.");
        // Note: Filters are handled server-side via form submission for this table
        initTableSorter('comparison-table'); // Enable client-side sorting
    }

    // --- Fund Duration Details Page ---
    const fundDurationTable = document.getElementById('fund-duration-table');
    if (fundDurationTable) {
        console.log("Fund duration details page table detected. Initializing sorter.");
        initTableSorter('fund-duration-table'); 
    }

    // --- Filters Drawer Logic ---
    const showFiltersBtn = document.getElementById('show-filters-btn');
    const closeFiltersBtn = document.getElementById('close-filters-btn');
    const filtersDrawer = document.getElementById('filters-drawer');

    if (showFiltersBtn && filtersDrawer && closeFiltersBtn) {
        console.log("Initializing filters drawer toggle.");
        showFiltersBtn.addEventListener('click', () => {
            console.log("Show filters clicked");
            filtersDrawer.classList.remove('translate-x-full');
            filtersDrawer.classList.add('translate-x-0'); // Although not strictly necessary if removing the other
        });

        closeFiltersBtn.addEventListener('click', () => {
            console.log("Close filters clicked");
            filtersDrawer.classList.add('translate-x-full');
            filtersDrawer.classList.remove('translate-x-0');
        });
    } else {
        console.log("Filters drawer elements not found, skipping initialization.");
        if (!showFiltersBtn) console.log("Missing: #show-filters-btn");
        if (!closeFiltersBtn) console.log("Missing: #close-filters-btn");
        if (!filtersDrawer) console.log("Missing: #filters-drawer");
    }

    // Add any other global initializations here
});

/**
 * Updates the navbar status bar with progress or a cleanup button.
 * @param {Object} opts - Options for the status bar.
 * @param {number} [opts.current] - Current completed steps.
 * @param {number} [opts.total] - Total steps.
 * @param {string} [opts.text] - Status text.
 * @param {boolean} [opts.complete] - If true, show cleanup button.
 * @param {boolean} [opts.error] - If true, show error style.
 */
function updateNavbarStatusBar({ current = 0, total = 0, text = '', complete = false, error = false } = {}) {
    const bar = document.getElementById('navbar-status-bar');
    if (!bar) return;
    bar.innerHTML = '';
    if (complete) {
        // Show cleanup button
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-success';
        btn.textContent = 'Run Data Clean up';
        btn.onclick = async () => {
            btn.disabled = true;
            btn.textContent = 'Cleaning...';
            try {
                const resp = await fetch('/run-cleanup', { method: 'POST' });
                const result = await resp.json();
                if (resp.ok && result.status === 'success') {
                    btn.textContent = 'Cleanup Complete!';
                    setTimeout(() => { bar.innerHTML = ''; }, 3000);
                } else {
                    btn.textContent = 'Cleanup Failed';
                    bar.innerHTML += `<span class='ms-2 text-danger'>${result.error || result.message || 'Error'}</span>`;
                }
            } catch (e) {
                btn.textContent = 'Cleanup Error';
                bar.innerHTML += `<span class='ms-2 text-danger'>Network error</span>`;
            } finally {
                setTimeout(() => { bar.innerHTML = ''; }, 5000);
            }
        };
        bar.appendChild(btn);
        return;
    }
    if (total > 0) {
        // Show progress bar
        const percent = Math.round((current / total) * 100);
        const progressDiv = document.createElement('div');
        progressDiv.className = 'progress';
        progressDiv.style.height = '16px';
        progressDiv.style.width = '70%';
        const progressBar = document.createElement('div');
        progressBar.className = 'progress-bar progress-bar-striped' + (error ? ' bg-danger' : '');
        progressBar.role = 'progressbar';
        progressBar.style.width = percent + '%';
        progressBar.ariaValueNow = percent;
        progressBar.ariaValueMin = 0;
        progressBar.ariaValueMax = 100;
        progressBar.textContent = percent + '%';
        progressDiv.appendChild(progressBar);
        bar.appendChild(progressDiv);
        // Status text
        const statusText = document.createElement('span');
        statusText.className = 'ms-2 small';
        statusText.textContent = text || `Processing ${current}/${total}`;
        bar.appendChild(statusText);
    } else if (text) {
        // Just show text
        const statusText = document.createElement('span');
        statusText.className = 'small';
        statusText.textContent = text;
        bar.appendChild(statusText);
    } else {
        bar.innerHTML = '';
    }
}

// Expose to global scope so inline scripts (non-module) can access it
window.updateNavbarStatusBar = updateNavbarStatusBar;