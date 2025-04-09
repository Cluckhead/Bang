// This file is responsible for dynamically creating and rendering the user interface elements
// related to charts and associated metric tables within the application.
// It separates the logic for generating the visual components from the main application flow.

// static/js/modules/ui/chartRenderer.js
// Handles creating DOM elements for charts and tables

import { createTimeSeriesChart } from '../charts/timeSeriesChart.js';
import { formatNumber } from '../utils/helpers.js';

/**
 * Renders charts and metric tables into the specified container.
 * @param {HTMLElement} container - The parent element to render into.
 * @param {object} chartsData - The chart data object from Flask.
 * @param {string} metricName - The name of the metric being displayed.
 * @param {string} latestDate - The latest date string.
 * @param {string[]} fundColNames - List of fund value column names.
 * @param {string} benchmarkColName - Name of the benchmark value column.
 */
export function renderChartsAndTables(container, chartsData, metricName, latestDate, fundColNames, benchmarkColName) {
    console.log("[chartRenderer] Rendering charts and tables for metric:", metricName, "Latest Date:", latestDate);
    console.log("[chartRenderer] Received Data:", JSON.parse(JSON.stringify(chartsData))); // Deep copy for logging
    console.log("[chartRenderer] Fund Column Names:", fundColNames);
    console.log("[chartRenderer] Benchmark Column Name:", benchmarkColName);
    
    container.innerHTML = ''; // Clear previous content

    if (!chartsData || Object.keys(chartsData).length === 0) {
        console.warn("[chartRenderer] No data available for metric:", metricName);
        container.innerHTML = '<p>No data available for this metric.</p>';
        return;
    }

    // Iterate through each fund's data (which is already sorted by max Change Z-score)
    for (const [fundCode, data] of Object.entries(chartsData)) {
        console.log(`[chartRenderer] Processing fund: ${fundCode}`);
        const metrics = data.metrics; // This is now the flattened metrics object
        // --- Use passed-in names, not names derived from potentially incomplete 'data' object ---
        const fundColumns = fundColNames; 
        const benchmarkColumn = benchmarkColName;
        console.log(`[chartRenderer] Fund ${fundCode} - Using Fund Columns:`, fundColumns);
        console.log(`[chartRenderer] Fund ${fundCode} - Using Benchmark Column:`, benchmarkColumn);
        console.log(`[chartRenderer] Fund ${fundCode} - Metrics Object:`, metrics);
        console.log(`[chartRenderer] Fund ${fundCode} - Full Data Object:`, JSON.parse(JSON.stringify(data))); // Deep copy
        
        // Find the maximum absolute *Change Z-Score* across all original columns for this fund
        let maxAbsZScore = 0;
        let zScoreForTitle = null; // Use the Z-score corresponding to the max absolute value
        if (metrics) {
            // Combine benchmark (if exists) and fund columns for checking Z-scores
            const colsToCheck = [];
            if (benchmarkColumn) colsToCheck.push(benchmarkColumn);
            if (fundColumns && Array.isArray(fundColumns)) colsToCheck.push(...fundColumns);
            
            console.log(`[chartRenderer] Fund ${fundCode} - Columns to check for Z-Score:`, colsToCheck);

            colsToCheck.forEach(colName => {
                if (!colName) return; // Skip null/empty column names
                const zScoreKey = `${colName} Change Z-Score`; 
                const zScore = metrics[zScoreKey];
                // console.log(`[chartRenderer] Fund ${fundCode} - Checking Z-Score for column '${colName}' (key: '${zScoreKey}'):`, zScore);
                 if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                     const absZ = Math.abs(zScore);
                     if (absZ > maxAbsZScore) {
                         maxAbsZScore = absZ;
                         zScoreForTitle = zScore; // Store this specific Z-score
                     }
                 }
            });
            console.log(`[chartRenderer] Fund ${fundCode} - Max Abs Z-Score found: ${maxAbsZScore}, Specific Z-Score for title: ${zScoreForTitle}`);
        } else {
            console.warn(`[chartRenderer] Fund ${fundCode} - Metrics object is missing or null.`);
        }

        // Determine CSS class based on the maximum Z-score for highlighting the whole section
        let zClass = '';
        if (maxAbsZScore > 3) { 
            zClass = 'very-high-z';
        } else if (maxAbsZScore > 2) {
            zClass = 'high-z';
        }
        console.log(`[chartRenderer] Fund ${fundCode} - Assigned Z-Class: '${zClass}'`);

        // Create wrapper div
        const wrapper = document.createElement('div');
        wrapper.className = `chart-container-wrapper ${zClass}`;
        wrapper.id = `chart-wrapper-${fundCode}`;

        // Add Duration Details Link (if applicable)
        if (metricName === 'Duration') {
            console.log(`[chartRenderer] Fund ${fundCode} - Adding Duration details link.`);
            const linkDiv = document.createElement('div');
            linkDiv.className = 'mb-2 text-end'; // Bootstrap 5 class for text alignment
            const link = document.createElement('a');
            // CORRECTED: Add the /fund/ prefix to the URL path
            link.href = `/fund/duration_details/${fundCode}`; 
            link.className = 'btn btn-info btn-sm';
            link.textContent = `View Security Duration Changes for ${fundCode} →`;
            linkDiv.appendChild(link);
            wrapper.appendChild(linkDiv); // Add link *before* chart
        }

        // Create Chart Canvas
        const canvas = document.createElement('canvas');
        canvas.id = `chart-${fundCode}`;
        canvas.className = 'chart-canvas';
        wrapper.appendChild(canvas);
        console.log(`[chartRenderer] Fund ${fundCode} - Created canvas with id: ${canvas.id}`);

        // Create Metrics Table using the *rewritten* function
        // Pass the specific fund/benchmark names from the *passed-in arguments*
        console.log(`[chartRenderer] Fund ${fundCode} - Calling createMetricsTable with:`, metrics, latestDate, fundColumns, benchmarkColumn, zClass);
        const table = createMetricsTable(metrics, latestDate, fundColumns, benchmarkColumn, zClass);
        wrapper.appendChild(table);
        console.log(`[chartRenderer] Fund ${fundCode} - Appended metrics table.`);

        container.appendChild(wrapper);
        console.log(`[chartRenderer] Fund ${fundCode} - Appended wrapper to container.`);

        // Render Chart
        // Use setTimeout to ensure the canvas is in the DOM and sized before drawing
        setTimeout(() => {
            console.log(`[chartRenderer] Fund ${fundCode} - Preparing to render chart in setTimeout.`);
             if (canvas.getContext('2d')) {
                 console.log(`[chartRenderer] Fund ${fundCode} - Canvas context obtained. Calling createTimeSeriesChart with:`, {
                    canvasId: canvas.id,
                    data: JSON.parse(JSON.stringify(data)), // Log deep copy
                    metricName: metricName,
                    fundCode: fundCode,
                    zScoreForTitle: zScoreForTitle,
                    is_missing_latest: data.is_missing_latest
                 });
                 // Pass zScoreForTitle (which is the max abs Change Z-Score across columns)
                 createTimeSeriesChart(canvas.id, data, metricName, fundCode, zScoreForTitle, data.is_missing_latest);
                 console.log(`[chartRenderer] Fund ${fundCode} - createTimeSeriesChart call finished.`);
            } else {
                console.error(`[chartRenderer] Fund ${fundCode} - Could not get 2D context for canvas ${canvas.id}`);
                const errorP = document.createElement('p');
                errorP.textContent = 'Error rendering chart.';
                errorP.className = 'text-danger';
                canvas.parentNode.replaceChild(errorP, canvas); // Replace canvas with error message
            }
        }, 0); 
    }
    console.log("[chartRenderer] Finished rendering all charts and tables.");
}

/**
 * Creates the *simplified* HTML table element displaying metrics for each original column.
 * @param {object | null} metrics - Flattened metrics object from Flask for a specific fund code.
 * @param {string} latestDate - The latest date string.
 * @param {string[]} fundColNames - List of fund value column names for this metric.
 * @param {string | null} benchmarkColName - Name of the benchmark value column for this metric (can be null).
 * @param {string} zClass - CSS class based on max Z-score (used for table highlight).
 * @returns {HTMLTableElement} The created table element.
 */
function createMetricsTable(metrics, latestDate, fundColNames, benchmarkColName, zClass) {
    console.log("[createMetricsTable] Creating table. Metrics:", metrics, "Latest Date:", latestDate, "Funds:", fundColNames, "Bench:", benchmarkColName, "zClass:", zClass);
    const table = document.createElement('table');
    // Apply overall highlight based on max Z across columns
    table.className = `table table-sm table-bordered metrics-table ${zClass}`;

    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    // Define the new, simpler headers
    headerRow.innerHTML = `
        <th>Column</th>
        <th>Latest Value (${latestDate})</th>
        <th>Change</th>
        <th>Mean</th> 
        <th>Max</th> 
        <th>Min</th> 
        <th>Change Z-Score</th> 
    `;

    const tbody = table.createTBody();

    if (!metrics) {
        console.warn("[createMetricsTable] Metrics object is null or undefined.");
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 7; // Match new header count
        cell.textContent = 'Metrics not available.';
        return table;
    }

    // Combine benchmark and fund columns for iteration
    const allColumns = [];
    if (benchmarkColName) allColumns.push(benchmarkColName);
    if (fundColNames && Array.isArray(fundColNames)) allColumns.push(...fundColNames);
    
    console.log("[createMetricsTable] Columns to create rows for:", allColumns);

    // Create one row per original column
    allColumns.forEach(colName => {
        if (!colName) {
            console.warn("[createMetricsTable] Skipping null/empty column name.");
            return; // Skip if column name is somehow empty
        }
        console.log(`[createMetricsTable] Creating row for column: ${colName}`);

        // Define the keys to access the flattened metrics object
        const latestValKey = `${colName} Latest Value`;
        const changeKey = `${colName} Change`;
        const meanKey = `${colName} Mean`;
        const maxKey = `${colName} Max`;
        const minKey = `${colName} Min`;
        const zScoreKey = `${colName} Change Z-Score`;

        const row = tbody.insertRow();
        
        // Determine cell class for Z-score highlighting on this specific row
        const zScoreValue = metrics[zScoreKey];
        let zScoreClass = '';
        // console.log(`[createMetricsTable] Column ${colName} - Z-Score Value: ${zScoreValue}`);
        if (zScoreValue !== null && typeof zScoreValue !== 'undefined' && !isNaN(zScoreValue)) {
             const absZ = Math.abs(zScoreValue);
             if (absZ > 3) { zScoreClass = 'very-high-z'; }
             else if (absZ > 2) { zScoreClass = 'high-z'; }
        }

        // Populate the row cells
        row.innerHTML = `
            <td>${colName}</td>
            <td>${formatNumber(metrics[latestValKey])}</td>
            <td>${formatNumber(metrics[changeKey])}</td>
            <td>${formatNumber(metrics[meanKey])}</td>
            <td>${formatNumber(metrics[maxKey])}</td>
            <td>${formatNumber(metrics[minKey])}</td>
            <td class="${zScoreClass}">${formatNumber(metrics[zScoreKey])}</td> 
        `; // Apply Z-score class only to the Z-score cell
        // console.log(`[createMetricsTable] Row HTML for ${colName}:`, row.innerHTML);
    });

    console.log("[createMetricsTable] Finished creating table.");
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
 * Renders multiple time series charts into the specified container for the fund detail page.
 * Iterates through metrics for a single fund.
 * @param {HTMLElement} container - The parent element to render into (e.g., #fundChartsArea).
 * @param {Array<object>} allChartData - An array where each object contains data for one metric's chart.
 *                                       Expected structure: [{ metricName: '...', labels: [...], datasets: [...] }, ...]
 */
export function renderFundCharts(container, allChartData) {
    console.log("[chartRenderer] Rendering charts for fund detail page.");
    console.log("[chartRenderer] Received Data:", JSON.parse(JSON.stringify(allChartData))); // Deep copy for logging
    
    container.innerHTML = ''; // Clear previous content

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
                 
                 createTimeSeriesChart(
                     canvas.id,         // The unique canvas ID
                     metricData,        // Data object with labels and datasets
                     metricName,        // Title prefix (e.g., "Yield")
                     null,              // fundCodeOrSecurityId (not needed for title)
                     null,              // zScoreForTitle (not applicable)
                     null               // is_missing_latest (not applicable)
                 );
                 console.log(`[chartRenderer] createTimeSeriesChart call finished for metric: ${metricName}.`);
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