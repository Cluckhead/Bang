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
 * @param {boolean} showSecondary - Whether to show secondary data in the metrics table.
 */
export function renderChartsAndTables(container, payload, showSecondary = true) {
    const metadata = payload.metadata;
    const fundsData = payload.funds; // Renamed from chartsData for clarity
    const metricName = metadata.metric_name;
    const latestDate = metadata.latest_date;
    // Keep original column names from metadata for table generation
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
    // Event listener will be attached by the caller (main.js)
    if (toggleContainer) {
        // Show toggle if *any* secondary data is potentially available based on metadata
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
            const chartDatasets = chartConfig.datasets;
            const chartMetrics = chartConfig.latest_metrics;
            const chartId = `${fundCode}-${chartType}`;

            console.log(`[chartRenderer] Creating elements for chart: ${chartId}`);

             // --- Create DOM Elements for Each Chart --- 
            const chartWrapper = document.createElement('div');
            // Add column class for side-by-side layout on large screens
            chartWrapper.className = `chart-container-wrapper chart-type-${chartType} col-lg-6`; 
            chartWrapper.id = `chart-wrapper-${chartId}`;

        // Create Chart Canvas
        const canvas = document.createElement('canvas');
            canvas.id = `chart-${chartId}`;
        canvas.className = 'chart-canvas';
            chartWrapper.appendChild(canvas);

            // Create Metrics Table (pass specific metrics and chart type)
        const table = createMetricsTable(
                chartMetrics,
            latestDate,
                chartType, // Pass chart type to determine columns
                metadata, // Pass full metadata for context
                showSecondary // Pass showSecondary
            );
            chartWrapper.appendChild(table);
            
            // Append chartWrapper to the row, not the fundWrapper directly
            chartsRow.appendChild(chartWrapper); 

        // --- Render Chart --- 
        setTimeout(() => {
            const chartCanvas = document.getElementById(canvas.id);
             if (chartCanvas && chartCanvas.getContext('2d')) {
                    console.log(`[chartRenderer] Rendering chart for ${chartId}`);
                    
                    // Prepare chart data object for the charting function
                    const chartDataForFunction = {
                        labels: chartLabels,
                        datasets: chartDatasets
                    };
                    
                    // Pass specific Z-score ONLY if it's the main chart
                    const zScoreForChartTitle = (chartType === 'main') ? primaryZScoreForTitle : null;

                    const chart = createTimeSeriesChart(
                        canvas.id, 
                        chartDataForFunction, // Pass the structured data
                        chartTitle, // Use the title from config
                        fundCode, // Keep fund code for context if needed
                        zScoreForChartTitle, // Pass main Z-score only to main chart
                        isMissingLatest, // Still relevant at fund level
                        chartType // Pass chartType so title logic is correct
                    );
                 if (chart) {
                        chartInstances[chartId] = chart; // Store chart instance with unique ID
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

        // Append the row containing the charts to the main fund wrapper
        fundWrapper.appendChild(chartsRow);

        container.appendChild(fundWrapper); // Add the fund's wrapper to the main container

    } // End loop through funds
    console.log("[chartRenderer] Finished processing all funds.");
}

/**
 * Updates the visibility of secondary/SP data datasets across all managed charts.
 * @param {boolean} show - Whether to show or hide the secondary/SP datasets.
 */
export function toggleSecondaryDataVisibility(show) { // Make sure this is exported if used by main.js
    console.log(`[chartRenderer] Toggling SP data visibility to: ${show}`);
    // Iterate through the centrally stored chart instances
    Object.entries(chartInstances).forEach(([chartId, chart]) => {
        if (!chart || typeof chart.destroy === 'undefined') { // Check if chart instance is valid
            console.warn(`[chartRenderer] Skipping invalid chart instance for ID: ${chartId}`);
            return;
        }
        let spDatasetToggled = false;
        try {
        chart.data.datasets.forEach((dataset, index) => {
            // Check the isSpData flag added from Python
            if (dataset.isSpData === true) {
                // Use setDatasetVisibility for better control than just 'hidden' property
                chart.setDatasetVisibility(index, show);
                    console.log(`[chartRenderer] Chart ${chart.canvas.id} (${chartId}) - Setting SP dataset ${index} ('${dataset.label}') visibility to ${show}`);
                spDatasetToggled = true;
            }
        });
        // Only update if an SP dataset was actually toggled for this chart
        if (spDatasetToggled) {
            chart.update(); // Update the chart to reflect visibility changes
                console.log(`[chartRenderer] Updated chart ${chart.canvas.id} (${chartId})`);
            }
        } catch (error) {
            console.error(`[chartRenderer] Error toggling visibility for chart ${chartId}:`, error);
             // Potentially remove the instance if it's causing persistent errors?
            // delete chartInstances[chartId]; 
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

    const secondaryAvailable = metadata.secondary_data_available; // Overall flag
    const primaryFundColsMeta = metadata.fund_col_names || [];
    const primaryBenchColMeta = metadata.benchmark_col_name;
    const secondaryFundColsMeta = metadata.secondary_fund_col_names || [];
    const secondaryBenchColMeta = metadata.secondary_benchmark_col_name;
    const secondaryPrefix = "S&P ";

    if (!metrics || Object.keys(metrics).length === 0) {
        console.warn(`[createMetricsTable] Metrics object is null or empty for chart type: ${chartType}.`);
        headerRow.innerHTML = '<th>Metrics</th>'; // Simple header
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.textContent = 'Metrics not available.';
        return table;
    }

    // --- Define Headers based on Chart Type --- 
    let headers = ['Column', `Latest Value (${latestDate})`, 'Change', 'Mean', 'Max', 'Min', 'Change Z-Score'];
    let secondaryHeaders = ['S&P Latest', 'S&P Change', 'S&P Mean', 'S&P Max', 'S&P Min', 'S&P Z-Score'];
    let showSecondaryColumns = false;

    if (showSecondary) {
        if (chartType === 'relative') {
            showSecondaryColumns = Object.keys(metrics).some(key => key.startsWith(secondaryPrefix + 'Relative '));
        } else { // chartType === 'main'
            showSecondaryColumns = Object.keys(metrics).some(key => key.startsWith(secondaryPrefix) && !key.startsWith(secondaryPrefix + 'Relative '));
        }
    }

    headerRow.innerHTML = `<th>${headers.join('</th><th>')}</th>` + 
                         (showSecondaryColumns ? `<th class="text-muted">${secondaryHeaders.join('</th><th class="text-muted">')}</th>` : '');

    // --- Populate Rows based on Chart Type --- 

    const addRow = (displayName, baseKey, isSecondary = false) => {
        const prefix = isSecondary ? secondaryPrefix : '';
        const fullBaseKey = prefix + baseKey;
        
        // Check if *any* metric exists for this base key and prefix
        const latestValKey = `${fullBaseKey} Latest Value`;
        const changeKey = `${fullBaseKey} Change`;
        const meanKey = `${fullBaseKey} Mean`;
        const maxKey = `${fullBaseKey} Max`;
        const minKey = `${fullBaseKey} Min`;
        const zScoreKey = `${fullBaseKey} Change Z-Score`;

        // Only add row if at least one relevant metric is present
        if (
            metrics.hasOwnProperty(latestValKey) || metrics.hasOwnProperty(changeKey) || 
            metrics.hasOwnProperty(meanKey) || metrics.hasOwnProperty(maxKey) || 
            metrics.hasOwnProperty(minKey) || metrics.hasOwnProperty(zScoreKey)
        ) {
            const row = tbody.insertRow();
            const zScore = metrics[zScoreKey];
            let zClass = '';
            if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                const absZ = Math.abs(zScore);
                if (absZ > 3) { zClass = 'very-high-z'; }
                else if (absZ > 2) { zClass = 'high-z'; }
        }
            row.className = zClass;
            
            row.insertCell().textContent = displayName;
            row.insertCell().textContent = formatNumber(metrics[latestValKey]);
            row.insertCell().textContent = formatNumber(metrics[changeKey]);
            row.insertCell().textContent = formatNumber(metrics[meanKey]);
            row.insertCell().textContent = formatNumber(metrics[maxKey]);
            row.insertCell().textContent = formatNumber(metrics[minKey]);
            row.insertCell().textContent = formatNumber(metrics[zScoreKey]);

            if (showSecondaryColumns && !isSecondary) {
                // Add placeholder cells if primary row but secondary columns shown
                for (let i = 0; i < secondaryHeaders.length; i++) {
                    row.insertCell().textContent = '-';
                }
            }
        } else if (isSecondary && showSecondaryColumns) {
            // Add secondary row even if primary version doesn't exist, but only if secondary columns are shown
            const row = tbody.insertRow();
            row.insertCell().textContent = displayName;
            row.insertCell().textContent = formatNumber(metrics[latestValKey]);
            row.insertCell().textContent = formatNumber(metrics[changeKey]);
            row.insertCell().textContent = formatNumber(metrics[meanKey]);
            row.insertCell().textContent = formatNumber(metrics[maxKey]);
            row.insertCell().textContent = formatNumber(metrics[minKey]);
            row.insertCell().textContent = formatNumber(metrics[zScoreKey]);
            
            // Add empty primary cells
             for (let i = 0; i < headers.length -1; i++) { // -1 for the name column
                 row.insertCell(1).textContent = '-'; // Insert after name
             }
             row.className = 'text-muted'; // Mute the secondary row
        }
    };
    
    const addPairedRow = (displayName, baseKey) => {
        const primaryExists = Object.keys(metrics).some(k => k.startsWith(baseKey) && !k.startsWith(secondaryPrefix));
        const secondaryExists = showSecondaryColumns && Object.keys(metrics).some(k => k.startsWith(secondaryPrefix + baseKey));

        if (primaryExists || secondaryExists) {
            const row = tbody.insertRow();
            const zScoreKey = `${baseKey} Change Z-Score`;
            const zScore = metrics[zScoreKey]; // Use primary Z for highlight
            let zClass = '';
            if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                const absZ = Math.abs(zScore);
                if (absZ > 3) { zClass = 'very-high-z'; }
                else if (absZ > 2) { zClass = 'high-z'; }
                }
            row.className = zClass;

            row.insertCell().textContent = displayName;
            // Primary Metrics
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Latest Value`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Change`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Mean`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Max`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[`${baseKey} Min`]) : '-';
            row.insertCell().textContent = primaryExists ? formatNumber(metrics[zScoreKey]) : '-';

            // Secondary Metrics (if columns are shown)
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
        // Add row specifically for 'Relative' if its metrics exist
        addPairedRow('Relative (Port - Bench)', 'Relative');
    } else { // chartType === 'main'
        // Add Benchmark row first if it exists
        if (primaryBenchColMeta) {
             addPairedRow(primaryBenchColMeta, primaryBenchColMeta);
        }
        // Add rows for Fund columns
        primaryFundColsMeta.forEach(fundCol => {
            addPairedRow(fundCol, fundCol);
        });
    }

    // Ensure tbody is not empty, add placeholder if needed
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
// REMOVED: export { toggleSecondaryDataVisibility }; // Export toggle function 