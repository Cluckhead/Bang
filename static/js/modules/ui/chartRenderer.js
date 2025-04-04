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

    // Iterate through each fund's data (which is already sorted by max Z)
    for (const [fundCode, data] of Object.entries(chartsData)) {
        const metrics = data.metrics;
        
        // Find the maximum absolute Z-score across all spreads for this fund
        let maxAbsZScore = 0;
        let zScoreForTitle = null;
        if (metrics) {
            fundColNames.forEach(fundCol => {
                const zScoreKey = `${fundCol} Spread Z-Score`;
                const zScore = metrics[zScoreKey];
                 if (zScore !== null && typeof zScore !== 'undefined') {
                     const absZ = Math.abs(zScore);
                     if (absZ > maxAbsZScore) {
                         maxAbsZScore = absZ;
                         zScoreForTitle = zScore; // Store the Z-score that corresponds to the max abs Z
                     }
                 }
            });
        }

        // Determine CSS class based on the maximum Z-score
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

        // Create Metrics Table (now handles multiple fund columns)
        const table = createMetricsTable(metrics, latestDate, fundColNames, benchmarkColName, zClass);
        wrapper.appendChild(table);

        container.appendChild(wrapper);

        // Render Chart
        setTimeout(() => {
             if (canvas.getContext('2d')) {
                 // Pass zScoreForTitle to be potentially used in chart title
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
 * Creates the HTML table element for displaying metrics for multiple fund columns.
 * @param {object | null} metrics - Metrics object containing data for all fund spreads.
 * @param {string} latestDate - The latest date string.
 * @param {string[]} fundColNames - List of fund value column names.
 * @param {string} benchmarkColName - Name of the benchmark value column.
 * @param {string} zClass - CSS class based on max Z-score.
 * @returns {HTMLTableElement} The created table element.
 */
function createMetricsTable(metrics, latestDate, fundColNames, benchmarkColName, zClass) {
    const table = document.createElement('table');
    table.className = `table table-sm table-bordered metrics-table ${zClass}`;

    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    headerRow.innerHTML = `
        <th>Metric</th>
        <th>Latest Value (${latestDate})</th>
        <th>Change from Previous</th>
        <th>Historical Spread</th>
        <th>Spread Z-Score</th>
    `; // Added Z-score column

    const tbody = table.createTBody();

    if (!metrics) {
        // Handle missing metrics
        const row = tbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 5; // Updated colspan
        cell.textContent = 'Metrics not available.';
        return table;
    }

    // Add Benchmark Row First (it's constant across fund columns)
    let benchRow = tbody.insertRow();
    benchRow.innerHTML = `
        <td>${benchmarkColName}</td>
        <td>${formatNumber(metrics[`Latest ${benchmarkColName}`])}</td>
        <td>N/A</td>
        <td colspan="2">N/A</td> {# No spread/Z for benchmark vs itself #}
    `;

    // Add rows for each Fund Column
    fundColNames.forEach(fundCol => {
        const spreadColName = `${fundCol} Spread`;
        const zScoreColName = `${spreadColName} Z-Score`;
        const fundChangeColName = `${fundCol} Change`;
        const spreadChangeColName = `${spreadColName} Change`;
        const histMeanColName = `${spreadColName} Mean`;
        const histStdDevColName = `${spreadColName} Std Dev`;

        // Fund Value Row
        let valRow = tbody.insertRow();
        valRow.innerHTML = `
            <td>${fundCol}</td>
            <td>${formatNumber(metrics[`Latest ${fundCol}`])}</td>
            <td>${formatNumber(metrics[fundChangeColName])}</td>
            <td>Mean: ${formatNumber(metrics[histMeanColName])}</td>
            <td rowspan="2"><strong>${formatNumber(metrics[zScoreColName])}</strong></td> {# Z-score spans two rows #}
        `;

        // Spread Row
        let spreadRow = tbody.insertRow();
        spreadRow.innerHTML = `
            <td><em>${spreadColName}</em></td>
            <td>${formatNumber(metrics[`Latest ${spreadColName}`])}</td>
            <td>${formatNumber(metrics[spreadChangeColName])}</td>
             <td>Std Dev: ${formatNumber(metrics[histStdDevColName])}</td>
        `;
        // Add a light border between fund column groups for clarity
        spreadRow.style.borderBottom = '2px solid #ccc'; 
    });

    return table;
} 