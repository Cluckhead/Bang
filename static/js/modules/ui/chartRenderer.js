// This file is responsible for dynamically creating and rendering the user interface elements
// related to charts and associated metric tables within the application.
// It separates the logic for generating the visual components from the main application flow.
// Updated to handle optional secondary data sources and toggle visibility.

// static/js/modules/ui/chartRenderer.js
// Handles creating DOM elements for charts and tables

import { createTimeSeriesChart } from '../charts/timeSeriesChart.js';
import { formatNumber } from '../utils/helpers.js';

// Store chart instances to manage them later (e.g., for toggling)
const chartInstances = {};

/**
 * Renders charts and metric tables into the specified container.
 * Handles primary and optional secondary (S&P) data source toggle.
 * @param {HTMLElement} container - The parent element to render into.
 * @param {object} payload - The full data payload object from Flask (contains metadata and funds data).
 */
export function renderChartsAndTables(container, payload) {
    const metadata = payload.metadata;
    const chartsData = payload.funds;
    const metricName = metadata.metric_name;
    const latestDate = metadata.latest_date;
    const fundColNames = metadata.fund_col_names;
    const benchmarkColName = metadata.benchmark_col_name;
    const secondaryDataAvailable = metadata.secondary_data_available;
    const secondaryFundColNames = metadata.secondary_fund_col_names;
    const secondaryBenchmarkColName = metadata.secondary_benchmark_col_name;

    console.log("[chartRenderer] Rendering charts for metric:", metricName, "Latest Date:", latestDate);
    console.log("[chartRenderer] Metadata:", metadata);
    console.log("[chartRenderer] Fund Data Keys:", Object.keys(chartsData || {}));

    // Clear previous content and chart instances
    container.innerHTML = '';
    Object.keys(chartInstances).forEach(key => delete chartInstances[key]);

    if (!chartsData || Object.keys(chartsData).length === 0) {
        console.warn("[chartRenderer] No fund data available for metric:", metricName);
        container.innerHTML = '<p>No fund data available for this metric.</p>';
        return;
    }

    // --- Setup Toggle Switch --- 
    const toggleContainer = document.getElementById('sp-toggle-container');
    const toggleSwitch = document.getElementById('toggleSpData');

    // Only control visibility of the container here
    // Event listener will be attached by the caller (main.js)
    if (toggleContainer) {
        if (secondaryDataAvailable) {
            console.log("[chartRenderer] Secondary data available, ensuring toggle container is visible.");
            toggleContainer.style.display = 'block'; // Show the toggle container
        } else {
            console.log("[chartRenderer] Secondary data not available, ensuring toggle container is hidden.");
            toggleContainer.style.display = 'none'; // Ensure toggle container is hidden
        }
    } else {
        console.warn("[chartRenderer] Toggle switch container not found in the DOM.");
    }

    // --- Render Chart and Table for Each Fund --- 
    for (const [fundCode, data] of Object.entries(chartsData)) {
        console.log(`[chartRenderer] Processing fund: ${fundCode}`);
        const metrics = data.metrics; // Flattened metrics for this fund
        const isMissingLatest = data.is_missing_latest;

        // Find max absolute Z-score from PRIMARY metrics for section highlight
        let maxAbsPrimaryZScore = 0;
        let primaryZScoreForTitle = null;
        if (metrics) {
            const primaryColsToCheck = [];
            if (benchmarkColName) primaryColsToCheck.push(benchmarkColName);
            if (fundColNames && Array.isArray(fundColNames)) primaryColsToCheck.push(...fundColNames);
            
            primaryColsToCheck.forEach(colName => {
                if (!colName) return;
                // Look for the non-prefixed Z-score key
                const zScoreKey = `${colName} Change Z-Score`; 
                const zScore = metrics[zScoreKey];
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

        // --- Create DOM Elements --- 
        const wrapper = document.createElement('div');
        wrapper.className = `chart-container-wrapper ${zClass}`;
        wrapper.id = `chart-wrapper-${fundCode}`;

        // Add Duration Details Link (if applicable)
        if (metricName === 'Duration') {
            const linkDiv = document.createElement('div');
            linkDiv.className = 'mb-2 text-end';
            const link = document.createElement('a');
            link.href = `/fund/duration_details/${fundCode}`;
            link.className = 'btn btn-info btn-sm';
            link.textContent = `View Security Duration Changes for ${fundCode} →`;
            linkDiv.appendChild(link);
            wrapper.appendChild(linkDiv);
        }

        // Create Chart Canvas
        const canvas = document.createElement('canvas');
        canvas.id = `chart-${fundCode}`;
        canvas.className = 'chart-canvas';
        wrapper.appendChild(canvas);

        // Create Metrics Table (handles primary and secondary columns)
        const table = createMetricsTable(
            metrics,
            latestDate,
            fundColNames,
            benchmarkColName,
            secondaryDataAvailable,
            secondaryFundColNames,
            secondaryBenchmarkColName,
            "S&P " // Prefix for secondary
        );
        wrapper.appendChild(table);
        container.appendChild(wrapper);

        // --- Render Chart --- 
        setTimeout(() => {
            const chartCanvas = document.getElementById(canvas.id);
             if (chartCanvas && chartCanvas.getContext('2d')) {
                 console.log(`[chartRenderer] Rendering chart for ${fundCode}`);
                 // Pass the specific Z-score corresponding to the max absolute primary Z
                 const chart = createTimeSeriesChart(canvas.id, data, metricName, fundCode, primaryZScoreForTitle, isMissingLatest);
                 if (chart) {
                     chartInstances[fundCode] = chart; // Store chart instance
                     console.log(`[chartRenderer] Stored chart instance for ${fundCode}`);
                 } else {
                      console.error(`[chartRenderer] Failed to create chart instance for ${fundCode}`);
                 }
            } else {
                console.error(`[chartRenderer] Could not get 2D context for canvas ${canvas.id}`);
                const errorP = document.createElement('p');
                errorP.textContent = 'Error rendering chart.';
                errorP.className = 'text-danger';
                if (chartCanvas && chartCanvas.parentNode) {
                    chartCanvas.parentNode.replaceChild(errorP, chartCanvas);
                } else if (wrapper) {
                    wrapper.appendChild(errorP);
                }
            }
        }, 0); 
    }
    console.log("[chartRenderer] Finished processing all funds.");
}

/**
 * Updates the visibility of secondary/SP data datasets across all managed charts.
 * @param {boolean} show - Whether to show or hide the secondary/SP datasets.
 */
function toggleSecondaryDataVisibility(show) {
    console.log(`[chartRenderer] Toggling SP data visibility to: ${show}`);
    // Iterate through the centrally stored chart instances
    Object.entries(chartInstances).forEach(([key, chart]) => {
        let spDatasetToggled = false;
        chart.data.datasets.forEach((dataset, index) => {
            // Check the isSpData flag added from Python
            if (dataset.isSpData === true) {
                // Use setDatasetVisibility for better control than just 'hidden' property
                chart.setDatasetVisibility(index, show);
                console.log(`[chartRenderer] Chart ${chart.canvas.id} - Setting SP dataset ${index} ('${dataset.label}') visibility to ${show}`);
                spDatasetToggled = true;
            }
        });
        // Only update if an SP dataset was actually toggled for this chart
        if (spDatasetToggled) {
            chart.update(); // Update the chart to reflect visibility changes
            console.log(`[chartRenderer] Updated chart ${chart.canvas.id}`);
        }
    });
}

/**
 * Creates the HTML table element displaying metrics.
 * Includes primary columns and optionally secondary (prefixed) columns.
 *
 * @param {object | null} metrics - Flattened metrics object from Flask.
 * @param {string} latestDate - The latest date string.
 * @param {string[]} fundColNames - List of primary fund value column names.
 * @param {string | null} benchmarkColName - Primary benchmark column name.
 * @param {boolean} secondaryAvailable - Flag indicating if secondary data exists.
 * @param {string[] | null} secondaryFundColNames - List of secondary fund value column names.
 * @param {string | null} secondaryBenchmarkColName - Secondary benchmark column name.
 * @param {string} secondaryPrefix - Prefix for secondary metric keys (e.g., "S&P ").
 * @returns {HTMLTableElement} The created table element.
 */
function createMetricsTable(
    metrics, 
    latestDate, 
    fundColNames, 
    benchmarkColName, 
    secondaryAvailable, 
    secondaryFundColNames, 
    secondaryBenchmarkColName, 
    secondaryPrefix
) {
    const table = document.createElement('table');
    table.className = 'table table-sm table-bordered metrics-table'; // Apply base classes

    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    // Define headers dynamically based on secondary data availability
    headerRow.innerHTML = `
        <th>Column</th>
        <th>Latest Value (${latestDate})</th>
        <th>Change</th>
        <th>Mean</th> 
        <th>Max</th> 
        <th>Min</th> 
        <th>Change Z-Score</th>
        ${secondaryAvailable ? `
        <th class="text-muted">S&P Latest</th>
        <th class="text-muted">S&P Change</th>
        <th class="text-muted">S&P Mean</th>
        <th class="text-muted">S&P Max</th>
        <th class="text-muted">S&P Min</th>
        <th class="text-muted">S&P Z-Score</th>
        ` : ''} 
    `;

    const tbody = table.createTBody();

    if (!metrics) {
        console.warn("[createMetricsTable] Metrics object is null.");
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = secondaryAvailable ? 13 : 7; // Adjust colspan based on headers
        cell.textContent = 'Metrics not available.';
        return table;
    }

    // Combine primary columns for iteration
    const allPrimaryColumns = [];
    if (benchmarkColName) allPrimaryColumns.push(benchmarkColName);
    if (fundColNames && Array.isArray(fundColNames)) allPrimaryColumns.push(...fundColNames);

    // Create one row per primary column
    allPrimaryColumns.forEach(colName => {
        if (!colName) return;

        const row = tbody.insertRow();
        
        // --- Primary Metrics --- 
        const pri_latestValKey = `${colName} Latest Value`;
        const pri_changeKey = `${colName} Change`;
        const pri_meanKey = `${colName} Mean`;
        const pri_maxKey = `${colName} Max`;
        const pri_minKey = `${colName} Min`;
        const pri_zScoreKey = `${colName} Change Z-Score`;

        const pri_zScoreValue = metrics[pri_zScoreKey];
        let pri_zScoreClass = ''; // Default class
        if (pri_zScoreValue !== null && typeof pri_zScoreValue !== 'undefined' && !isNaN(pri_zScoreValue)) {
             const absZ = Math.abs(pri_zScoreValue);
             if (absZ > 3) { pri_zScoreClass = 'very-high-z'; }
             else if (absZ > 2) { pri_zScoreClass = 'high-z'; }
        }

        // Populate primary cells
        row.innerHTML = `
            <td>${colName}</td>
            <td>${formatNumber(metrics[pri_latestValKey])}</td>
            <td>${formatNumber(metrics[pri_changeKey])}</td>
            <td>${formatNumber(metrics[pri_meanKey])}</td>
            <td>${formatNumber(metrics[pri_maxKey])}</td>
            <td>${formatNumber(metrics[pri_minKey])}</td>
            <td class="${pri_zScoreClass}">${formatNumber(pri_zScoreValue)}</td>
        `;

        // --- Secondary Metrics (if available) --- 
        if (secondaryAvailable) {
            // Try to find the corresponding secondary column name (simple exact match)
            let secColName = null;
            if (benchmarkColName === colName && secondaryBenchmarkColName) {
                secColName = secondaryBenchmarkColName;
            } else if (secondaryFundColNames && secondaryFundColNames.includes(colName)) {
                secColName = colName;
            }
            
            let secCellsHTML = '<td colspan="6" class="text-muted text-center">(N/A)</td>'; // Default placeholder
            
            // Check if a corresponding secondary column exists and has metrics
            if (secColName && `${secondaryPrefix}${secColName} Latest Value` in metrics) {
                const sec_latestValKey = `${secondaryPrefix}${secColName} Latest Value`;
                const sec_changeKey = `${secondaryPrefix}${secColName} Change`;
                const sec_meanKey = `${secondaryPrefix}${secColName} Mean`;
                const sec_maxKey = `${secondaryPrefix}${secColName} Max`;
                const sec_minKey = `${secondaryPrefix}${secColName} Min`;
                const sec_zScoreKey = `${secondaryPrefix}${secColName} Change Z-Score`;

                const sec_zScoreValue = metrics[sec_zScoreKey];
                let sec_zScoreClass = 'text-muted'; // Default secondary class
                if (sec_zScoreValue !== null && typeof sec_zScoreValue !== 'undefined' && !isNaN(sec_zScoreValue)) {
                    const absZ = Math.abs(sec_zScoreValue);
                    // Apply similar Z-score highlighting, but keep text muted unless significant
                    if (absZ > 3) { sec_zScoreClass = 'very-high-z text-muted'; } 
                    else if (absZ > 2) { sec_zScoreClass = 'high-z text-muted'; } 
                }
                
                secCellsHTML = `
                    <td class="text-muted">${formatNumber(metrics[sec_latestValKey])}</td>
                    <td class="text-muted">${formatNumber(metrics[sec_changeKey])}</td>
                    <td class="text-muted">${formatNumber(metrics[sec_meanKey])}</td>
                    <td class="text-muted">${formatNumber(metrics[sec_maxKey])}</td>
                    <td class="text-muted">${formatNumber(metrics[sec_minKey])}</td>
                    <td class="${sec_zScoreClass}">${formatNumber(sec_zScoreValue)}</td>
                `;
            } else if (secColName) {
                // If secColName was found but metrics weren't in the object (e.g., secondary processing failed for this col)
                secCellsHTML = '<td colspan="6" class="text-muted text-center">(Metrics missing)</td>';
            }
            // Append the secondary cells (either data or placeholder)
            row.innerHTML += secCellsHTML;
        }
    });

    console.log("[createMetricsTable] Table created.");
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
    console.log("[chartRenderer] Received Data:", JSON.parse(JSON.stringify(allChartData))); // Deep copy for logging
    
    container.innerHTML = ''; // Clear previous content
    // Clear previous chart instances for this specific rendering context
    Object.keys(chartInstances).forEach(key => delete chartInstances[key]); 

    if (!allChartData || !Array.isArray(allChartData) || allChartData.length === 0) {
        console.warn("[chartRenderer] No chart data provided for the fund page.");
        // Message should be handled by the template, but log it here.
        return;
    }

    // Iterate through each metric's chart data
    allChartData.forEach((metricData, index) => {
        if (!metricData || !metricData.metricName || !metricData.labels || !metricData.datasets) {
            console.warn(`[chartRenderer] Skipping chart at index ${index} due to missing data:`, metricData);
            return;
        }

        const metricName = metricData.metricName;
        const safeMetricName = metricName.replace(/[^a-zA-Z0-9]/g, '-') || 'metric'; // Create a CSS-safe ID part
        console.log(`[chartRenderer] Processing metric: ${metricName}`);

        // Create wrapper div for each chart (using Bootstrap columns for layout)
        const wrapper = document.createElement('div');
        // Uses the col classes defined in the template's fundChartsArea (row-cols-1 row-cols-lg-2)
        wrapper.className = `chart-container-wrapper fund-chart-item`; 
        wrapper.id = `fund-chart-wrapper-${safeMetricName}-${index}`;

        // Create Chart Canvas
        const canvas = document.createElement('canvas');
        // Ensure unique ID for each canvas
        canvas.id = `fund-chart-${safeMetricName}-${index}`; 
        canvas.className = 'chart-canvas';
        wrapper.appendChild(canvas);
        console.log(`[chartRenderer] Created canvas with id: ${canvas.id} for metric: ${metricName}`);

        // Append the wrapper to the main container
        container.appendChild(wrapper);
        console.log(`[chartRenderer] Appended wrapper for ${metricName} to container.`);

        // Render Chart using the existing time series chart function
        // Use setTimeout to ensure the canvas is in the DOM and sized
        setTimeout(() => {
            console.log(`[chartRenderer] Preparing to render chart for metric: ${metricName} in setTimeout.`);
             if (canvas.getContext('2d')) {
                 console.log(`[chartRenderer] Canvas context obtained. Calling createTimeSeriesChart with:`, {
                    canvasId: canvas.id,
                    data: JSON.parse(JSON.stringify(metricData)), // Log deep copy
                    titlePrefix: metricName, // Use metric name as the main title part
                    fundCodeOrSecurityId: null, // Not needed for title here
                    zScoreForTitle: null, // No specific Z-score for the whole page/chart
                    is_missing_latest: null // Not applicable here
                 });
                 
                 // Create the chart AND store the instance
                 const chartInstance = createTimeSeriesChart(
                     canvas.id,         // The unique canvas ID
                     metricData,        // Data object with labels and datasets
                     metricName,        // Title prefix (e.g., "Yield")
                     null,              // fundCodeOrSecurityId (not needed for title)
                     null,              // zScoreForTitle (not applicable)
                     null               // is_missing_latest (not applicable)
                 );
                 
                 if (chartInstance) {
                     // Store the instance in the module-level object
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
                canvas.parentNode.replaceChild(errorP, canvas); // Replace canvas with error message
            }
        }, 0); 
    });

    console.log("[chartRenderer] Finished rendering all fund charts.");
} 

// Export necessary functions
export { toggleSecondaryDataVisibility }; // Export toggle function 