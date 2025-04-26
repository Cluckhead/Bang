// This file is responsible for dynamically creating and rendering the user interface elements
// related to charts and associated metric tables within the application.
// It separates the logic for generating the visual components from the main application flow.
// Updated to handle optional secondary data sources and toggle visibility.
// Added 'Inspect' button and modal functionality for contribution analysis.

// static/js/modules/ui/chartRenderer.js
// Handles creating DOM elements for charts and tables

import { createTimeSeriesChart } from '../charts/timeSeriesChart.js';
import { formatNumber, getIsoDateString } from '../utils/helpers.js'; // Import helper for date formatting

// Store chart instances to manage them later (e.g., for toggling)
const chartInstances = {};

/**
 * Renders charts and metric tables into the specified container.
 * Handles primary and optional secondary (S&P) data source toggle.
 * @param {HTMLElement} container - The parent element to render into.
 * @param {object} payload - The full data payload object from Flask (contains metadata and funds data).
 * @param {boolean} showSecondary - Whether to show secondary data in the metrics table.
 */
export function renderChartsAndTables(container, payload, showSecondary = true) {
    const metadata = payload.metadata;
    const fundsData = payload.funds; // Renamed from chartsData for clarity
    const metricName = metadata.metric_name;
    const latestDate = metadata.latest_date; // Expecting YYYY-MM-DD format from backend
    const primaryFundColsMeta = metadata.fund_col_names;
    const primaryBenchColMeta = metadata.benchmark_col_name;
    const secondaryFundColsMeta = metadata.secondary_fund_col_names;
    const secondaryBenchColMeta = metadata.secondary_benchmark_col_name;
    const secondaryDataAvailableOverall = metadata.secondary_data_available;

    console.log("[chartRenderer] Rendering charts for metric:", metricName, "Latest Date:", latestDate);
    console.log("[chartRenderer] Metadata:", metadata);
    console.log("[chartRenderer] Fund Data Keys:", Object.keys(fundsData || {}));

    // Clear previous content and chart instances
    container.innerHTML = '';
    Object.keys(chartInstances).forEach(key => {
        try {
            chartInstances[key]?.destroy(); // Properly destroy old chart instances
        } catch (e) {
            console.warn(`Error destroying chart instance ${key}:`, e);
        }
        delete chartInstances[key];
    });

    if (!fundsData || Object.keys(fundsData).length === 0) {
        console.warn("[chartRenderer] No fund data available for metric:", metricName);
        container.innerHTML = '<p>No fund data available for this metric.</p>';
        return;
    }

    // --- Setup Toggle Switch --- 
    const toggleContainer = document.getElementById('sp-toggle-container');
    if (toggleContainer) {
        if (secondaryDataAvailableOverall) {
            console.log("[chartRenderer] Overall secondary data available, ensuring toggle container is visible.");
            toggleContainer.style.display = 'block'; 
        } else {
            console.log("[chartRenderer] Overall secondary data not available, ensuring toggle container is hidden.");
            toggleContainer.style.display = 'none'; 
        }
    } else {
        console.warn("[chartRenderer] Toggle switch container not found in the DOM.");
    }

    // --- Create Modal Structure (once per page load) --- 
    if (!document.getElementById('inspectModal')) {
        createInspectModal();
        
        // Add event listener for the submit button ONCE after creating the modal
        const submitBtn = document.getElementById('inspectSubmitBtn');
        if (submitBtn) {
            submitBtn.removeEventListener('click', handleInspectSubmit); 
            submitBtn.addEventListener('click', handleInspectSubmit);
            console.log("[chartRenderer] Submit button event listener attached.");
        } else {
            console.error("[chartRenderer] Inspect modal submit button not found after creation!");
        }
    } else {
        // Ensure submit listener is attached even if modal existed (e.g., partial page update)
        const submitBtn = document.getElementById('inspectSubmitBtn');
         if (submitBtn && !submitBtn.hasAttribute('data-listener-attached')) {
             submitBtn.removeEventListener('click', handleInspectSubmit);
             submitBtn.addEventListener('click', handleInspectSubmit);
             submitBtn.setAttribute('data-listener-attached', 'true');
             console.log("[chartRenderer] Submit button event listener RE-attached.");
         }
    }
    
    // --- Render Charts and Tables for Each Fund --- 
    // Sort fundsData by max absolute Z-score (descending)
    const sortedFunds = Object.entries(fundsData).map(([fundCode, fundData]) => {
        let maxAbsPrimaryZScore = 0;
        const mainChartConfig = (fundData.charts || []).find(c => c.chart_type === 'main');
        if (mainChartConfig && mainChartConfig.latest_metrics) {
            const mainMetrics = mainChartConfig.latest_metrics;
            const primaryColsToCheck = [];
            if (primaryBenchColMeta) primaryColsToCheck.push(primaryBenchColMeta);
            if (primaryFundColsMeta && Array.isArray(primaryFundColsMeta)) primaryColsToCheck.push(...primaryFundColsMeta);
            primaryColsToCheck.forEach(colName => {
                if (!colName) return;
                const zScoreKey = `${colName} Change Z-Score`;
                const zScore = mainMetrics[zScoreKey];
                if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                    const absZ = Math.abs(zScore);
                    if (absZ > maxAbsPrimaryZScore) {
                        maxAbsPrimaryZScore = absZ;
                    }
                }
            });
        }
        return { fundCode, fundData, maxAbsPrimaryZScore };
    }).sort((a, b) => b.maxAbsPrimaryZScore - a.maxAbsPrimaryZScore);

    for (const { fundCode, fundData } of sortedFunds) {
        console.log(`[chartRenderer] Processing fund: ${fundCode}`);
        const charts = fundData.charts || [];
        const isMissingLatest = fundData.is_missing_latest;

        // Find max absolute Z-score from PRIMARY MAIN metrics for section highlight
        let maxAbsPrimaryZScore = 0;
        let primaryZScoreForTitle = null;
        const mainChartConfig = charts.find(c => c.chart_type === 'main');
        if (mainChartConfig && mainChartConfig.latest_metrics) {
            const mainMetrics = mainChartConfig.latest_metrics;
            const primaryColsToCheck = [];
            if (primaryBenchColMeta) primaryColsToCheck.push(primaryBenchColMeta);
            if (primaryFundColsMeta && Array.isArray(primaryFundColsMeta)) primaryColsToCheck.push(...primaryFundColsMeta);
            
            primaryColsToCheck.forEach(colName => {
                if (!colName) return;
                const zScoreKey = `${colName} Change Z-Score`; 
                const zScore = mainMetrics[zScoreKey];
                 if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                     const absZ = Math.abs(zScore);
                     if (absZ > maxAbsPrimaryZScore) {
                         maxAbsPrimaryZScore = absZ;
                         primaryZScoreForTitle = zScore; 
                     }
                 }
            });
        }

        // Determine CSS class for the wrapper based on primary Z-score
        let zClass = '';
        if (maxAbsPrimaryZScore > 3) { zClass = 'very-high-z'; }
        else if (maxAbsPrimaryZScore > 2) { zClass = 'high-z'; }

        // Create a main wrapper for the fund
        const fundWrapper = document.createElement('div');
        fundWrapper.className = `fund-wrapper ${zClass}`; // Use a different class for the outer wrapper
        fundWrapper.id = `fund-wrapper-${fundCode}`;

        // Add Duration Details Link (if applicable) - Moved to fund level
        if (metricName === 'Duration') {
            const linkDiv = document.createElement('div');
            linkDiv.className = 'mb-2 text-end';
            const link = document.createElement('a');
            link.href = `/fund/duration_details/${fundCode}`;
            link.className = 'btn btn-info btn-sm';
            link.textContent = `View Security Duration Changes for ${fundCode} →`;
            linkDiv.appendChild(link);
            fundWrapper.appendChild(linkDiv);
        }

        // Create a row container for the charts within this fund
        const chartsRow = document.createElement('div');
        chartsRow.className = 'row'; // Bootstrap row class

        // Now loop through the charts for this fund (Relative first, then Main)
        charts.forEach(chartConfig => {
            const chartType = chartConfig.chart_type;
            const chartTitle = chartConfig.title;
            const chartLabels = chartConfig.labels;
            let chartDatasets = chartConfig.datasets;
            if (!showSecondary) {
                chartDatasets = chartDatasets.filter(ds => !ds.isSpData);
            } else {
                chartDatasets = chartDatasets.map(ds => {
                    if (ds.isSpData) {
                        return { ...ds, hidden: false };
                    }
                    return { ...ds };
                });
            }
            const chartMetrics = chartConfig.latest_metrics;
            const chartId = `${fundCode}-${chartType}`;

            console.log(`[chartRenderer] Creating elements for chart: ${chartId}`);

             // --- Create DOM Elements for Each Chart --- 
            const chartWrapper = document.createElement('div');
            chartWrapper.className = `chart-container-wrapper chart-type-${chartType} col-lg-6 mb-3`; 
            chartWrapper.id = `chart-wrapper-${chartId}`;
            chartWrapper.style.position = 'relative';

            // --- Add Inspect Button (WITHOUT data-* attributes for toggle) --- 
            const inspectButton = document.createElement('button');
            inspectButton.textContent = 'Inspect';
            inspectButton.className = 'btn btn-outline-secondary btn-sm inspect-button';
            inspectButton.style.position = 'absolute';
            inspectButton.style.top = '5px';
            inspectButton.style.right = '5px';
            // Still add data attributes for our handler to read
            inspectButton.dataset.metricName = metricName;
            inspectButton.dataset.fundCode = fundCode;
            inspectButton.dataset.latestDate = latestDate || getIsoDateString(new Date());
            // REMOVE Bootstrap 4 modal attributes 
            // inspectButton.setAttribute('data-toggle', 'modal'); 
            // inspectButton.setAttribute('data-target', '#inspectModal'); 
            
            // --- Add DIRECT Click Listener --- 
            inspectButton.addEventListener('click', handleInspectButtonClick);
            
            chartWrapper.appendChild(inspectButton);

            // Create Chart Canvas
            const canvas = document.createElement('canvas');
            canvas.id = `chart-${chartId}`;
            canvas.className = 'chart-canvas';
            chartWrapper.appendChild(canvas);

            // Create Metrics Table
            const table = createMetricsTable(
                chartMetrics,
                latestDate,
                chartType,
                metadata,
                showSecondary
            );
            chartWrapper.appendChild(table);
            
            chartsRow.appendChild(chartWrapper); 

            // --- Render Chart (setTimeout remains) --- 
            setTimeout(() => {
                 const chartCanvas = document.getElementById(canvas.id);
                 if (chartCanvas && chartCanvas.getContext('2d')) {
                    console.log(`[chartRenderer] Rendering chart for ${chartId}`);
                    const chartDataForFunction = {
                        labels: chartLabels,
                        datasets: chartDatasets
                    };
                    const zScoreForChartTitle = (chartType === 'main') ? primaryZScoreForTitle : null;
                    const chart = createTimeSeriesChart(
                        canvas.id, 
                        chartDataForFunction, 
                        chartTitle, 
                        fundCode, 
                        zScoreForChartTitle, 
                        isMissingLatest, 
                        chartType 
                    );
                     if (chart) {
                            chartInstances[chartId] = chart; 
                            console.log(`[chartRenderer] Stored chart instance for ${chartId}`);
                     } else {
                            console.error(`[chartRenderer] Failed to create chart instance for ${chartId}`);
                     }
                } else {
                    console.error(`[chartRenderer] Could not get 2D context for canvas ${canvas.id}`);
                    const errorP = document.createElement('p');
                    errorP.textContent = 'Error rendering chart.';
                    errorP.className = 'text-danger';
                    if (chartCanvas && chartCanvas.parentNode) {
                        chartCanvas.parentNode.replaceChild(errorP, chartCanvas);
                    } else if (chartWrapper) {
                        chartWrapper.appendChild(errorP);
                    }
                }
            }, 0); 
        }); // End loop through charts for the fund

        fundWrapper.appendChild(chartsRow);
        container.appendChild(fundWrapper); 

    } // End loop through funds
    console.log("[chartRenderer] Finished processing all funds.");
}

// --- NEW: Direct button click handler (adapted for BS4/jQuery) --- 
function handleInspectButtonClick(event) {
    const button = event.currentTarget;
    console.log("[Inspect Button] Clicked:", button);

    // 1. Populate the data FIRST (using the existing separate function)
    // Create a mock event object for populateInspectModalData
    const mockEvent = { 
        relatedTarget: button, 
        currentTarget: document.getElementById('inspectModal') // Ensure modal element exists
    };
    if (!mockEvent.currentTarget) {
        console.error("[Inspect Button] Modal element #inspectModal not found when preparing to populate!");
        return;
    }
    populateInspectModalData(mockEvent); // Call data population function

    // 2. Show the modal using Bootstrap 4 jQuery method
    try {
        // Use jQuery selector and Bootstrap 4 modal method
        const modalElement = document.getElementById('inspectModal'); // Get element for logging
        if (!modalElement) throw new Error("Modal element #inspectModal not found for jQuery selector.");
        
        if (typeof $ !== 'undefined' && $.fn.modal) {
            $('#inspectModal').modal('show'); 
            console.log("[Inspect Button] Modal shown via jQuery $('#inspectModal').modal('show').");
        } else {
            console.error("[Inspect Button] jQuery or Bootstrap modal function not available.");
            alert("Error: Could not trigger modal. jQuery or Bootstrap JS might be missing.");
        }
    } catch (e) {
        console.error("[Inspect Button] Error showing modal via jQuery/BS4 API:", e);
        alert("Could not open inspect modal. Check console for errors.");
    }
}

// --- Function to populate modal data (called by click handler now) --- 
function populateInspectModalData(event) {
    const button = event.relatedTarget;
    if (!button) {
        console.error("[Modal Populate] No relatedTarget provided in the event");
        return;
    }

    // --- DEBUG: Log the button element and its attributes --- 
    console.log("[Modal Populate] Triggering Button:", button);
    console.log("[Modal Populate] Button data-metric-name:", button.getAttribute('data-metric-name'));
    console.log("[Modal Populate] Button data-fund-code:", button.getAttribute('data-fund-code'));
    console.log("[Modal Populate] Button dataset:", JSON.stringify(button.dataset));
    // --- END DEBUG --- 

    const metricName = button.dataset.metricName || button.getAttribute('data-metric-name');
    const fundCode = button.dataset.fundCode || button.getAttribute('data-fund-code');
    const latestDateStr = button.dataset.latestDate || button.getAttribute('data-latest-date');

    // --- DEBUG: Log the retrieved values --- 
    console.log(`[Modal Populate] Retrieved - Metric: ${metricName}, Fund: ${fundCode}, Date: ${latestDateStr}`);
    // --- END DEBUG --- 

    if (!metricName || !fundCode) {
        console.error("[Modal Populate] Missing data attributes on button AFTER retrieval attempt:", {
            metricName,
            fundCode,
            latestDateStr,
            buttonHTML: button.outerHTML
        });
        // Populate with placeholders to avoid breaking UI further down, but log error
        // metricName = 'Error'; 
        // fundCode = 'Error';
    }

    const modalElement = event.currentTarget;

    // Populate modal title/text
    const modalTitle = modalElement.querySelector('#inspectModalLabel');
    const metricNameSpan = modalElement.querySelector('#inspectModalMetricName');
    const fundCodeSpan = modalElement.querySelector('#inspectModalFundCode');
    
    if (modalTitle) modalTitle.textContent = `Inspect Contribution - ${metricName || 'Unknown'} (${fundCode || 'Unknown'})`;
    if (metricNameSpan) metricNameSpan.textContent = metricName || 'Unknown';
    if (fundCodeSpan) fundCodeSpan.textContent = fundCode || 'Unknown';

    // Set default dates
    const endDateInput = modalElement.querySelector('#inspectEndDate');
    const startDateInput = modalElement.querySelector('#inspectStartDate');
    if (endDateInput && startDateInput) {
        endDateInput.value = latestDateStr || getIsoDateString(new Date());
        try {
            const endDate = new Date(endDateInput.value);
            const startDate = new Date(endDate);
            startDate.setMonth(startDate.getMonth() - 1);
            startDateInput.value = getIsoDateString(startDate);
        } catch (e) {
            console.error("Error setting default start date:", e);
            const today = new Date();
            const defaultStartDate = new Date(today);
            defaultStartDate.setMonth(defaultStartDate.getMonth() - 1);
            startDateInput.value = getIsoDateString(defaultStartDate);
            if (!latestDateStr) endDateInput.value = getIsoDateString(today);
        }
    } else {
        console.error("[Modal Populate] Date input fields not found in modal!");
    }

    // Clear previous error messages
    const errorMsgDiv = document.getElementById('inspectErrorMsg');
    if(errorMsgDiv) {
        errorMsgDiv.textContent = '';
        errorMsgDiv.style.display = 'none';
    }
    
    // Store data needed for submit handler on the modal itself
    // --- DEBUG: Log the data being stored --- 
    console.log("[Modal Populate] Storing data on modal:", { metricName: metricName || '', fundCode: fundCode || '' });
    // --- END DEBUG --- 
    modalElement.dataset.metricName = metricName || '';
    modalElement.dataset.fundCode = fundCode || '';
    modalElement.setAttribute('data-metric-name', metricName || '');
    modalElement.setAttribute('data-fund-code', fundCode || '');
    window.currentInspectData = {
        metricName: metricName || '',
        fundCode: fundCode || ''
    };
    
    // Reset submit button state
    const submitBtn = document.getElementById('inspectSubmitBtn');
    if(submitBtn){
        submitBtn.disabled = false;
        submitBtn.textContent = 'Analyze';
    }
}

/**
 * Handles the submission of the inspect modal.
 * Fetches contribution data and redirects to the results page.
 */
async function handleInspectSubmit() {
    const modalElement = document.getElementById('inspectModal');
    let metricName = '';
    let fundCode = '';
    
    // --- Retrieve stored data (priority: window > dataset > attribute) ---
    if (window.currentInspectData) {
        metricName = window.currentInspectData.metricName;
        fundCode = window.currentInspectData.fundCode;
    } else if (modalElement) {
        metricName = modalElement.dataset.metricName || modalElement.getAttribute('data-metric-name') || '';
        fundCode = modalElement.dataset.fundCode || modalElement.getAttribute('data-fund-code') || '';
    }
    console.log("[Inspect] Submit using data:", { metricName, fundCode });

    // --- Get Dates AND Data Source --- 
    const startDate = document.getElementById('inspectStartDate').value;
    const endDate = document.getElementById('inspectEndDate').value;
    const dataSourceSelected = document.querySelector('input[name="inspectDataSource"]:checked');
    const dataSource = dataSourceSelected ? dataSourceSelected.value : 'Original'; // Default to Original if none selected
    
    const errorMsgDiv = document.getElementById('inspectErrorMsg');
    const submitBtn = document.getElementById('inspectSubmitBtn');

    // --- Validation --- 
    if (!startDate || !endDate) {
        errorMsgDiv.textContent = 'Please select both a start and end date.';
        errorMsgDiv.style.display = 'block';
        return;
    }
    if (new Date(startDate) >= new Date(endDate)) {
        errorMsgDiv.textContent = 'Start date must be before end date.';
        errorMsgDiv.style.display = 'block';
        return;
    }
    if (!metricName || !fundCode) {
        console.error("[Inspect] Missing required data for submission", { metricName, fundCode }); // Keep detailed log
        errorMsgDiv.textContent = 'Missing metric name or fund code information. Please close modal and try again.';
        errorMsgDiv.style.display = 'block';
        return;
    }
    if (!dataSource) { // Should have default, but check anyway
        errorMsgDiv.textContent = 'Please select a data source (Original or S&P).';
        errorMsgDiv.style.display = 'block';
        return;
    }

    errorMsgDiv.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Analyzing...';

    try {
        const apiUrl = `/metric/${encodeURIComponent(metricName)}/inspect`;
        const requestBody = { 
            fund_code: fundCode,
            start_date: startDate, 
            end_date: endDate,
            data_source: dataSource // Include data source in the request
        };
        console.log(`[Inspect] Sending POST to ${apiUrl} with body:`, requestBody);

        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json' 
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            let errorJson = {};
            try { errorJson = await response.json(); } catch (parseError) { /* ignore */ }
            const errorText = errorJson.error || `Error ${response.status}: ${response.statusText}`;
            throw new Error(errorText);
        }

        const resultsData = await response.json();
        console.log("[Inspect] API Success. Response:", resultsData);

        // Redirect to results page
        const resultsUrl = `/metric/inspect/results?metric_name=${encodeURIComponent(metricName)}&fund_code=${encodeURIComponent(fundCode)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&data_source=${encodeURIComponent(dataSource)}`; // Pass data source
        window.location.href = resultsUrl;
        
        // Close modal (may not happen due to redirect)
        const modal = $('#inspectModal').modal('hide'); // Use jQuery for BS4 hide just in case

    } catch (error) {
        console.error("[Inspect] Fetch Error:", error);
        errorMsgDiv.textContent = `Analysis failed: ${error.message}`;
        errorMsgDiv.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Analyze';
    }
}

/**
 * Creates the Bootstrap modal structure and appends it to the body.
 */
function createInspectModal() {
     const modalHtml = `
        <div class="modal fade" id="inspectModal" tabindex="-1" role="dialog" aria-labelledby="inspectModalLabel" aria-hidden="true">
            <div class="modal-dialog" role="document">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="inspectModalLabel">Inspect Contribution</h5>
                        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <div class="modal-body">
                        <p>Analyze contribution to the change in <strong id="inspectModalMetricName">[Metric]</strong> for fund <strong id="inspectModalFundCode">[Fund]</strong>.</p>
                        
                        <!-- Date Range Selection -->
                        <div class="form-group">
                            <label for="inspectStartDate" class="form-label">Start Date (Exclusive)</label>
                            <input type="date" class="form-control" id="inspectStartDate" required>
                        </div>
                        <div class="form-group">
                            <label for="inspectEndDate" class="form-label">End Date (Inclusive)</label>
                            <input type="date" class="form-control" id="inspectEndDate" required>
                        </div>

                        <!-- Data Source Selection -->
                        <div class="form-group">
                            <label class="form-label">Data Source:</label>
                            <div>
                                <div class="form-check form-check-inline">
                                    <input class="form-check-input" type="radio" name="inspectDataSource" id="inspectDataSourceOriginal" value="Original" checked>
                                    <label class="form-check-label" for="inspectDataSourceOriginal">Original</label>
                                </div>
                                <div class="form-check form-check-inline">
                                    <input class="form-check-input" type="radio" name="inspectDataSource" id="inspectDataSourceSP" value="SP">
                                    <label class="form-check-label" for="inspectDataSourceSP">S&P</label>
                                </div>
                            </div>
                        </div>
                        
                        <div id="inspectErrorMsg" class="text-danger mt-2" style="display: none;"></div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" id="inspectSubmitBtn">Analyze</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    console.log("[chartRenderer] Inspect modal HTML created.");
}

/**
 * Updates the visibility of secondary/SP data datasets across all managed charts.
 * @param {boolean} show - Whether to show or hide the secondary/SP datasets.
 */
export function toggleSecondaryDataVisibility(show) {
    console.log(`[chartRenderer] Toggling SP data visibility to: ${show}`);
    Object.entries(chartInstances).forEach(([chartId, chart]) => {
        if (!chart || typeof chart.destroy === 'undefined') { 
            console.warn(`[chartRenderer] Skipping invalid chart instance for ID: ${chartId}`);
            return;
        }
        let spDatasetToggled = false;
        try {
        chart.data.datasets.forEach((dataset, index) => {
            if (dataset.isSpData === true) {
                chart.setDatasetVisibility(index, show);
                    console.log(`[chartRenderer] Chart ${chart.canvas.id} (${chartId}) - Setting SP dataset ${index} ('${dataset.label}') visibility to ${show}`);
                spDatasetToggled = true;
            }
        });
        if (spDatasetToggled) {
            chart.update(); 
                console.log(`[chartRenderer] Updated chart ${chart.canvas.id} (${chartId})`);
            }
        } catch (error) {
            console.error(`[chartRenderer] Error toggling visibility for chart ${chartId}:`, error);
        }
    });
}

/**
 * Creates the HTML table element displaying metrics for a specific chart.
 *
 * @param {object | null} metrics - Metrics object specific to this chart (relative or main).
 * @param {string} latestDate - The latest date string.
 * @param {string} chartType - 'relative' or 'main'.
 * @param {object} metadata - The overall metadata object from Flask (for column names).
 * @param {boolean} showSecondary - Whether to show secondary data in the metrics table.
 * @returns {HTMLTableElement} The created table element.
 */
function createMetricsTable(
    metrics, 
    latestDate, 
    chartType, 
    metadata, 
    showSecondary = true
) {
    const table = document.createElement('table');
    table.className = 'table table-sm table-bordered metrics-table';

    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    const tbody = table.createTBody();

    const secondaryAvailable = metadata.secondary_data_available; 
    const primaryFundColsMeta = metadata.fund_col_names || [];
    const primaryBenchColMeta = metadata.benchmark_col_name;
    const secondaryFundColsMeta = metadata.secondary_fund_col_names || [];
    const secondaryBenchColMeta = metadata.secondary_benchmark_col_name;
    const secondaryPrefix = "S&P ";

    if (!metrics || Object.keys(metrics).length === 0) {
        console.warn(`[createMetricsTable] Metrics object is null or empty for chart type: ${chartType}.`);
        headerRow.innerHTML = '<th>Metrics</th>';
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.textContent = 'Metrics not available.';
        return table;
    }

    let headers = ['Column', `Latest Value (${latestDate})`, 'Change', 'Mean', 'Max', 'Min', 'Change Z-Score'];
    let secondaryHeaders = ['S&P Latest', 'S&P Change', 'S&P Mean', 'S&P Max', 'S&P Min', 'S&P Z-Score'];
    let showSecondaryColumns = false;

    if (showSecondary) {
        if (chartType === 'relative') {
            showSecondaryColumns = Object.keys(metrics).some(key => key.startsWith(secondaryPrefix + 'Relative '));
        } else { 
            showSecondaryColumns = Object.keys(metrics).some(key => key.startsWith(secondaryPrefix) && !key.startsWith(secondaryPrefix + 'Relative '));
        }
    }

    headerRow.innerHTML = `<th>${headers.join('</th><th>')}</th>` + 
                         (showSecondaryColumns ? `<th class="text-muted">${secondaryHeaders.join('</th><th class="text-muted">')}</th>` : '');

    const addPairedRow = (displayName, baseKey) => {
        const primaryExists = Object.keys(metrics).some(k => k.startsWith(baseKey) && !k.startsWith(secondaryPrefix));
        const secondaryExists = showSecondaryColumns && Object.keys(metrics).some(k => k.startsWith(secondaryPrefix + baseKey));

        if (primaryExists || secondaryExists) {
            const row = tbody.insertRow();
            const zScoreKey = `${baseKey} Change Z-Score`;
            const zScore = metrics[zScoreKey]; 
            let zClass = '';
            if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                const absZ = Math.abs(zScore);
                if (absZ > 3) { zClass = 'very-high-z'; }
                else if (absZ > 2) { zClass = 'high-z'; }
                }
            row.className = zClass;

            row.insertCell().textContent = displayName;
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Latest Value`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Change`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Mean`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Max`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Min`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[zScoreKey]) : '-';

            if (showSecondaryColumns) {
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Latest Value`]) : '-';
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Change`]) : '-';
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Mean`]) : '-';
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Max`]) : '-';
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Min`]) : '-';
                row.insertCell().textContent = secondaryExists ? formatNumber(metrics[`${secondaryPrefix}${baseKey} Change Z-Score`]) : '-';
            }
        }
    };


    if (chartType === 'relative') {
        addPairedRow('Relative (Port - Bench)', 'Relative');
    } else { 
        if (primaryBenchColMeta) {
             addPairedRow(primaryBenchColMeta, primaryBenchColMeta);
        }
        primaryFundColsMeta.forEach(fundCol => {
            addPairedRow(fundCol, fundCol);
        });
    }

    if (tbody.rows.length === 0) {
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = headers.length + (showSecondaryColumns ? secondaryHeaders.length : 0);
        cell.textContent = 'No relevant metrics found for this chart.';
    }

    return table;
} 

/**
 * Renders a single time series chart for a specific security.
 * @param {string} canvasId - The ID of the canvas element.
 * @param {object} chartData - The chart data (labels, datasets) from Flask.
 * @param {string} securityId - The ID of the security.
 * @param {string} metricName - The name of the metric.
 */
export function renderSingleSecurityChart(canvasId, chartData, securityId, metricName) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
        console.error(`Canvas element with ID '${canvasId}' not found.`);
        return;
    }
    if (!chartData || !chartData.labels || !chartData.datasets) {
        console.error('Invalid or incomplete chart data provided.');
        ctx.parentElement.innerHTML = '<p class="text-danger">Error: Invalid chart data.</p>';
        return;
    }

    try {
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: chartData.datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: `${securityId} - ${metricName} Time Series`,
                        font: { size: 16 }
                    },
                    legend: {
                        position: 'top',
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Date'
                        }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: `${metricName} Value`
                        },
                        beginAtZero: false,
                        ticks: {
                            maxTicksLimit: 8
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Price'
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                        beginAtZero: false
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index',
                },
            }
        });
        console.log(`Chart rendered for ${securityId} - ${metricName}`);
    } catch (error) {
        console.error(`Error creating chart for ${securityId} - ${metricName}:`, error);
        ctx.parentElement.innerHTML = '<p class="text-danger">Error rendering chart.</p>';
    }
}

/**
 * Renders multiple charts onto a single page (like the Fund Detail page).
 * Stores created chart instances in the module-level 'chartInstances' object.
 * @param {HTMLElement} container - The parent element to render into.
 * @param {Array<object>} allChartData - An array of chart data objects, each with metricName, labels, datasets.
 */
export function renderFundCharts(container, allChartData) {
    console.log("[chartRenderer] Rendering charts for fund detail page.");
    console.log("[chartRenderer] Received Data:", JSON.parse(JSON.stringify(allChartData)));
    
    container.innerHTML = ''; 
    Object.keys(chartInstances).forEach(key => delete chartInstances[key]); 

    if (!allChartData || !Array.isArray(allChartData) || allChartData.length === 0) {
        console.warn("[chartRenderer] No chart data provided for the fund page.");
        return;
    }

    allChartData.forEach((metricData, index) => {
        if (!metricData || !metricData.metricName || !metricData.labels || !metricData.datasets) {
            console.warn(`[chartRenderer] Skipping chart at index ${index} due to missing data:`, metricData);
            return;
        }

        const metricName = metricData.metricName;
        const safeMetricName = metricName.replace(/[^a-zA-Z0-9]/g, '-') || 'metric'; 
        console.log(`[chartRenderer] Processing metric: ${metricName}`);

        const wrapper = document.createElement('div');
        wrapper.className = `chart-container-wrapper fund-chart-item`; 
        wrapper.id = `fund-chart-wrapper-${safeMetricName}-${index}`;

        const canvas = document.createElement('canvas');
        canvas.id = `fund-chart-${safeMetricName}-${index}`; 
        canvas.className = 'chart-canvas';
        wrapper.appendChild(canvas);
        console.log(`[chartRenderer] Created canvas with id: ${canvas.id} for metric: ${metricName}`);

        container.appendChild(wrapper);
        console.log(`[chartRenderer] Appended wrapper for ${metricName} to container.`);

        setTimeout(() => {
            console.log(`[chartRenderer] Preparing to render chart for metric: ${metricName} in setTimeout.`);
             if (canvas.getContext('2d')) {
                 console.log(`[chartRenderer] Canvas context obtained. Calling createTimeSeriesChart with:`, {
                    canvasId: canvas.id,
                    data: JSON.parse(JSON.stringify(metricData)), 
                    titlePrefix: metricName, 
                    fundCodeOrSecurityId: null, 
                    zScoreForTitle: null, 
                    is_missing_latest: null 
                 });
                 
                 const chartInstance = createTimeSeriesChart(
                     canvas.id,         
                     metricData,        
                     metricName,        
                     null,              
                     null,              
                     null               
                 );
                 
                 if (chartInstance) {
                     chartInstances[canvas.id] = chartInstance;
                     console.log(`[chartRenderer] Stored chart instance for ${metricName} with key ${canvas.id}`);
                 } else {
                     console.error(`[chartRenderer] Failed to get chart instance for metric: ${metricName}`);
                 }
            } else {
                console.error(`[chartRenderer] Could not get 2D context for canvas ${canvas.id} (Metric: ${metricName})`);
                const errorP = document.createElement('p');
                errorP.textContent = `Error rendering chart for ${metricName}.`;
                errorP.className = 'text-danger';
                canvas.parentNode.replaceChild(errorP, canvas); 
            }
        }, 0); 
    });

    console.log("[chartRenderer] Finished rendering all fund charts.");
} 