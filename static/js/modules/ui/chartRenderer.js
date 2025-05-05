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

    // Get skeleton element and clear previous content/chart instances
    const skeleton = document.getElementById('loadingSkeleton');
    container.innerHTML = ''; // Clear previous charts/tables/content but keep skeleton initially

    Object.keys(chartInstances).forEach(key => {
        try {
            chartInstances[key]?.destroy(); // Properly destroy old chart instances
        } catch (e) {
            console.warn(`Error destroying chart instance ${key}:`, e);
        }
        delete chartInstances[key];
    });

    // Hide skeleton and show message if no data
    if (!fundsData || Object.keys(fundsData).length === 0) {
        console.warn("[chartRenderer] No fund data available for metric:", metricName);
        if (skeleton) skeleton.style.display = 'none'; // Hide skeleton
        container.innerHTML = '<div class="bg-[#F7F7F7] rounded-lg shadow-[0_0_4px_rgba(0,0,0,0.06)] p-4 text-center text-gray-600">No fund data available for this metric.</div>'; // Styled message
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

    // Hide skeleton before starting to render actual charts
    if (skeleton) {
        skeleton.style.display = 'none';
        console.log("[chartRenderer] Hid loading skeleton.");
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

        // *** NEW: Extract metrics before the loop ***
        const mainChartConfig = charts.find(c => c.chart_type === 'main');
        const relativeChartConfig = charts.find(c => c.chart_type === 'relative');
        const mainMetrics = mainChartConfig ? mainChartConfig.latest_metrics : {};
        const relativeMetrics = relativeChartConfig ? relativeChartConfig.latest_metrics : {};
        // *** END NEW ***

        // Find max absolute Z-score from PRIMARY MAIN metrics for section highlight
        let maxAbsPrimaryZScore = 0;
        let primaryZScoreForTitle = null;
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
        // Use Tailwind flex wrap, remove Bootstrap gutter (g-4)
        chartsRow.className = 'flex flex-wrap -mx-2'; // Added -mx-2 for negative margin compensation for px-2 on columns

        // Now loop through the charts for this fund (Main and Relative)
        charts.forEach(chartConfig => {
            const chartType = chartConfig.chart_type;
            // *** Adjust title for relative chart ***
            const chartTitle = chartType === 'relative' ? `${fundCode} - Relative ${metricName}` : chartConfig.title;
            const chartLabels = chartConfig.labels;
            let chartDatasets = chartConfig.datasets;

            // *** ADDED LOG ***
            console.log(`[chartRenderer] Inside loop for fund ${fundCode}. Processing chartConfig:`, JSON.parse(JSON.stringify(chartConfig)));

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
            const chartCard = document.createElement('div');
            chartCard.className = 'bg-[#F7F7F7] rounded-lg shadow-[0_0_4px_rgba(0,0,0,0.06)] p-4 hover:shadow-md transition-shadow mb-4 w-full'; // Added w-full for consistency within column
            chartCard.id = `chart-card-${chartId}`;

            const chartWrapper = document.createElement('div');
            chartWrapper.className = `chart-container-wrapper chart-type-${chartType} h-80`; // REMOVED w-full
            chartWrapper.id = `chart-wrapper-${chartId}`;
            chartWrapper.style.position = 'relative';

            // --- Add Inspect Button (VANILLA JS, NO BOOTSTRAP) --- 
            const inspectButton = document.createElement('button');
            inspectButton.textContent = 'Inspect';
            inspectButton.className = 'inspect-btn px-3 py-1 rounded-md bg-secondary text-white hover:bg-secondary-dark text-sm mt-2';
            inspectButton.style.position = 'absolute';
            inspectButton.style.top = '5px';
            inspectButton.style.right = '5px';
            inspectButton.dataset.fund = fundCode;
            inspectButton.dataset.metric = metricName;
            // Gather all dates from all charts for this fund
            let allDates = [];
            (fundData.charts || []).forEach(chartConfig => {
                if (Array.isArray(chartConfig.labels)) {
                    allDates = allDates.concat(chartConfig.labels);
                }
            });
            allDates = Array.from(new Set(allDates)).sort(); // deduplicate and sort
            inspectButton.dataset.minDate = allDates[0] || '';
            inspectButton.dataset.maxDate = allDates[allDates.length - 1] || '';
            // No Bootstrap data-toggle/data-target
            // No jQuery event handler
            // Attach click event directly to open the modal
            inspectButton.addEventListener('click', function(e) {
                const btn = e.currentTarget;
                const inspectModal = document.getElementById('inspectModal');
                const inspectForm = document.getElementById('inspectForm');
                document.getElementById('inspectFund').value = btn.dataset.fund;
                document.getElementById('inspectMetric').value = btn.dataset.metric;
                document.getElementById('inspectStartDate').min = btn.dataset.minDate;
                document.getElementById('inspectStartDate').max = btn.dataset.maxDate;
                document.getElementById('inspectEndDate').min = btn.dataset.minDate;
                document.getElementById('inspectEndDate').max = btn.dataset.maxDate;
                document.getElementById('inspectStartDate').value = btn.dataset.minDate;
                document.getElementById('inspectEndDate').value = btn.dataset.maxDate;
                inspectForm.action = `/metric/${btn.dataset.metric}/inspect`;
                inspectModal.classList.remove('hidden');
            });
            chartWrapper.appendChild(inspectButton);

            // Create Chart Canvas
            const canvas = document.createElement('canvas');
            canvas.id = `chart-${chartId}`;
            canvas.className = 'w-full h-full';
            chartWrapper.appendChild(canvas);

            // Append chart wrapper (canvas) to the card
            chartCard.appendChild(chartWrapper);

            // *** Create a column wrapper for the card ***
            const colWrapper = document.createElement('div');
            // Use Tailwind responsive width classes instead of Bootstrap col-*
            // Added px-2 for gutter
            colWrapper.className = 'w-full lg:w-1/2 px-2 mb-4'; // Added mb-4 for vertical spacing when stacked
            colWrapper.appendChild(chartCard);

            // Append the column wrapper (containing the card) to the row
            chartsRow.appendChild(colWrapper);

            // --- Render Chart (setTimeout remains) --- 
            setTimeout(() => {
                 const chartCanvas = document.getElementById(canvas.id);
                 if (chartCanvas && chartCanvas.getContext('2d')) {
                    console.log(`[chartRenderer] Rendering chart for ${chartId}`);
                    const chartDataForFunction = {
                        labels: chartLabels,
                        datasets: chartDatasets
                    };
                    // *** Pass the potentially simplified chartTitle ***
                    const zScoreForChartTitle = (chartType === 'main') ? primaryZScoreForTitle : null;
                    const chart = createTimeSeriesChart(
                        canvas.id, 
                        chartDataForFunction, 
                        chartTitle, // Use modified title
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
                    } else if (chartCard) {
                        chartCard.appendChild(errorP);
                    }
                }
            }, 0); 
        }); // End loop through charts for the fund

        // Append the row (containing all chart columns for this fund) to the main fund wrapper
        fundWrapper.appendChild(chartsRow); // This should be correct - row is appended after loop

        // *** NEW: Create and append the consolidated metrics table AFTER the charts row ***
        const consolidatedTable = createMetricsTable(
            mainMetrics,         // Pass main metrics
            relativeMetrics,     // Pass relative metrics
            latestDate,
            metadata,
            showSecondary,
            fundCode             // Pass fund code for context
        );
        if (consolidatedTable) { // Only append if table was created
             fundWrapper.appendChild(consolidatedTable);
        }
        // *** END NEW ***

        // Append the complete fund wrapper to the main container
        container.appendChild(fundWrapper); 

    } // End loop through funds
    console.log("[chartRenderer] Finished processing all funds.");

    // Hide skeleton and show error in container if error occurred during rendering
    // (Error handling within createTimeSeriesChart already adds message to chart card, 
    // but this handles broader errors in chartRenderer itself if needed)
    // Example: if container remains empty after loop despite having data
    if (container.innerHTML.trim() === '' && skeleton && skeleton.style.display !== 'none') { 
        skeleton.style.display = 'none';
        container.innerHTML = '<div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative shadow-sm" role="alert">An error occurred while rendering charts.</div>';
    }
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
 * Creates the HTML table element displaying consolidated metrics for a fund section.
 *
 * @param {object} mainMetrics - Metrics object for the main chart.
 * @param {object} relativeMetrics - Metrics object for the relative chart.
 * @param {string} latestDate - The latest date string.
 * @param {object} metadata - The overall metadata object from Flask (for column names).
 * @param {boolean} showSecondary - Whether to show secondary data in the metrics table.
 * @param {string} fundCode - The fund code for context.
 * @returns {HTMLTableElement | null} The created table element, or null if no data.
 */
function createMetricsTable(
    mainMetrics,
    relativeMetrics,
    latestDate,
    metadata,
    showSecondary = true,
    fundCode
) {
    const table = document.createElement('table');
    table.className = 'mt-4 text-xs text-right'; 

    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    headerRow.className = 'border-b border-gray-300';
    
    const tbody = table.createTBody();
    tbody.className = 'divide-y divide-gray-200';

    const secondaryAvailable = metadata.secondary_data_available;
    const primaryFundColsMeta = metadata.fund_col_names || [];
    const primaryBenchColMeta = metadata.benchmark_col_name;
    const secondaryPrefix = "S&P ";

    if ((!mainMetrics || Object.keys(mainMetrics).length === 0) && 
        (!relativeMetrics || Object.keys(relativeMetrics).length === 0)) {
        console.warn(`[createMetricsTable] Both main and relative metrics are empty for fund: ${fundCode}.`);
        return null;
    }

    // Headers are now fixed, no S&P columns
    let headers = ['Field', `Latest (${latestDate})`, 'Change', 'Mean', 'Max', 'Min', 'Z-Score'];

    // Generate fixed headers
    const headerHtml = headers.map((h, index) => {
        const alignClass = (index === 0) ? 'text-left' : 'text-right'; 
        return `<th class="py-2 px-2 font-medium text-gray-600 uppercase tracking-wider ${alignClass}">${h}</th>`;
    }).join('');
    headerRow.innerHTML = headerHtml;

    // New function to add a single row (primary or secondary)
    const addMetricRow = (metricsSource, rowType, displayName, baseKey, isSecondary = false) => {
        const prefix = isSecondary ? secondaryPrefix : '';
        const fullBaseKey = prefix + baseKey;

        // Check if data exists for this specific row (primary or secondary)
        const dataExists = metricsSource && Object.keys(metricsSource).some(k => k.startsWith(fullBaseKey));
        if (!dataExists) {
            // console.debug(`[addMetricRow] Skipping row: No data for Type: ${rowType}, Key: ${fullBaseKey}`);
            return; // Silently skip if no data for this specific metric (e.g., only primary exists, skip secondary attempt)
        }

        const row = tbody.insertRow();
        const zScoreKey = `${fullBaseKey} Change Z-Score`;
        const zScore = metricsSource[zScoreKey];
        let zClass = '';
        if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
            const absZ = Math.abs(zScore);
            if (absZ > 3) { zClass = 'very-high-z'; }
            else if (absZ > 2) { zClass = 'high-z'; }
        }
        row.className = zClass;

        // Cell creation helper remains the same
        const createCell = (text, alignLeft = false) => {
            const cell = row.insertCell();
            cell.className = `py-2 px-2 ${alignLeft ? 'text-left' : 'text-right'}`;
            cell.textContent = text;
            return cell;
        };

        // Field name - add prefix if secondary
        const fieldDisplayName = isSecondary ? `S&P ${displayName}` : displayName;

        createCell(fieldDisplayName, true); // Field name (left aligned)
        // Use nullish coalescing for cleaner fallback
        createCell(formatNumber(metricsSource[`${fullBaseKey} Latest Value`]) ?? '-');
        createCell(formatNumber(metricsSource[`${fullBaseKey} Change`]) ?? '-');
        createCell(formatNumber(metricsSource[`${fullBaseKey} Mean`]) ?? '-');
        createCell(formatNumber(metricsSource[`${fullBaseKey} Max`]) ?? '-');
        createCell(formatNumber(metricsSource[`${fullBaseKey} Min`]) ?? '-');
        createCell(formatNumber(metricsSource[zScoreKey]) ?? '-'); // Z-Score
    };
    
    // New function to process a pair (primary + optional secondary)
    const processMetricPair = (metricsSource, rowType, displayName, baseKey) => {
        const primaryExists = metricsSource && Object.keys(metricsSource).some(k => k.startsWith(baseKey) && !k.startsWith(secondaryPrefix));
        const secondaryExists = secondaryAvailable && metricsSource && Object.keys(metricsSource).some(k => k.startsWith(secondaryPrefix + baseKey));

        if (primaryExists) {
            addMetricRow(metricsSource, rowType, displayName, baseKey, false); // Add primary row
        }
        // Add secondary row ONLY if showSecondary toggle is true AND data exists
        if (showSecondary && secondaryExists) { 
            addMetricRow(metricsSource, rowType, displayName, baseKey, true); // Add secondary row
        }
    };

    // Call processMetricPair for main benchmark, main fund columns, and relative metrics
    if (mainMetrics && Object.keys(mainMetrics).length > 0) {
        if (primaryBenchColMeta) {
             processMetricPair(mainMetrics, 'Main', primaryBenchColMeta, primaryBenchColMeta);
        }
        primaryFundColsMeta.forEach(fundCol => {
            processMetricPair(mainMetrics, 'Main', fundCol, fundCol);
        });
    }

    if (relativeMetrics && Object.keys(relativeMetrics).length > 0) {
        // Process Relative metric pair
        processMetricPair(relativeMetrics, 'Relative', 'Relative (Port - Bench)', 'Relative');
    }

    if (tbody.rows.length === 0) {
        const row = tbody.insertRow();
        const cell = row.insertCell();
        // Adjust colspan for the fixed number of headers
        cell.colSpan = headers.length; 
        cell.textContent = 'No relevant metrics found for this fund.';
        cell.className = 'text-center py-2 px-2';
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