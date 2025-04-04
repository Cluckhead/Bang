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
    container.innerHTML = ''; // Clear previous content

    if (Object.keys(chartsData).length === 0) {
        container.innerHTML = '<p>No data available for this metric.</p>';
        return;
    }

    // Iterate through each fund's data (which is already sorted by max Change Z-score)
    for (const [fundCode, data] of Object.entries(chartsData)) {
        const metrics = data.metrics; // This is now the flattened metrics object
        const fundColumns = data.fund_column_names; // Get passed fund columns
        const benchmarkColumn = data.benchmark_column_name; // Get passed benchmark column
        
        // Find the maximum absolute *Change Z-Score* across all original columns for this fund
        let maxAbsZScore = 0;
        let zScoreForTitle = null; // Use the Z-score corresponding to the max absolute value
        if (metrics) {
            const colsToCheck = [benchmarkColumn, ...fundColumns];
            colsToCheck.forEach(colName => {
                const zScoreKey = `${colName} Change Z-Score`; 
                const zScore = metrics[zScoreKey];
                 if (zScore !== null && typeof zScore !== 'undefined' && !isNaN(zScore)) {
                     const absZ = Math.abs(zScore);
                     if (absZ > maxAbsZScore) {
                         maxAbsZScore = absZ;
                         zScoreForTitle = zScore; // Store this specific Z-score
                     }
                 }
            });
        }

        // Determine CSS class based on the maximum Z-score for highlighting the whole section
        let zClass = '';
        if (maxAbsZScore > 3) { 
            zClass = 'very-high-z';
        } else if (maxAbsZScore > 2) {
            zClass = 'high-z';
        }

        // Create wrapper div
        const wrapper = document.createElement('div');
        wrapper.className = `chart-container-wrapper ${zClass}`;
        wrapper.id = `chart-wrapper-${fundCode}`;

        // Create Chart Canvas
        const canvas = document.createElement('canvas');
        canvas.id = `chart-${fundCode}`;
        canvas.className = 'chart-canvas';
        wrapper.appendChild(canvas);

        // Create Metrics Table using the *rewritten* function
        // Pass the specific fund/benchmark names from the data object
        const table = createMetricsTable(metrics, latestDate, fundColumns, benchmarkColumn, zClass);
        wrapper.appendChild(table);

        container.appendChild(wrapper);

        // Render Chart
        setTimeout(() => {
             if (canvas.getContext('2d')) {
                 // Pass zScoreForTitle (which is the max abs Change Z-Score across columns)
                 createTimeSeriesChart(canvas.id, data, metricName, fundCode, zScoreForTitle, data.is_missing_latest);
            } else {
                console.error(`Could not get 2D context for canvas ${canvas.id}`);
                const errorP = document.createElement('p');
                errorP.textContent = 'Error rendering chart.';
                errorP.className = 'text-danger';
                canvas.parentNode.replaceChild(errorP, canvas);
            }
        }, 0); 
    }
}

/**
 * Creates the *simplified* HTML table element displaying metrics for each original column.
 * @param {object | null} metrics - Flattened metrics object from Flask for a specific fund code.
 * @param {string} latestDate - The latest date string.
 * @param {string[]} fundColNames - List of fund value column names for this metric.
 * @param {string} benchmarkColName - Name of the benchmark value column for this metric.
 * @param {string} zClass - CSS class based on max Z-score (used for table highlight).
 * @returns {HTMLTableElement} The created table element.
 */
function createMetricsTable(metrics, latestDate, fundColNames, benchmarkColName, zClass) {
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
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 7; // Match new header count
        cell.textContent = 'Metrics not available.';
        return table;
    }

    // Combine benchmark and fund columns for iteration
    const allColumns = [benchmarkColName, ...fundColNames];

    // Create one row per original column
    allColumns.forEach(colName => {
        if (!colName) return; // Skip if column name is somehow empty

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
    });

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