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

import { renderChartsAndTables, renderSingleSecurityChart } from './modules/ui/chartRenderer.js';
import { initSecurityTableFilter } from './modules/ui/securityTableFilter.js';
import { initTableSorter } from './modules/ui/tableSorter.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // --- Metric Page (Multiple Charts) ---    
    const chartDataElement = document.getElementById('chartData');
    const chartsArea = document.getElementById('chartsArea');

    if (chartDataElement && chartsArea) {
        console.log("Metric page detected. Initializing charts.");
        try {
            const chartData = JSON.parse(chartDataElement.textContent);
            if (chartData) {
                renderChartsAndTables(chartData, chartsArea);
            } else {
                console.warn('Chart data is empty or invalid.');
            }
        } catch (error) {
            console.error('Error parsing chart data or rendering charts:', error);
            chartsArea.innerHTML = '<div class="alert alert-danger">Error loading chart data.</div>';
        }
    } else {
        // console.log("Chart data element or charts area not found, skipping multi-chart rendering.");
    }

    // --- Securities Summary Page (Filterable & Sortable Table) ---
    const securitiesTable = document.getElementById('securities-table');
    if (securitiesTable) {
        console.log("Securities page table detected. Initializing filters and sorter.");
        initSecurityTableFilter('securities-table');
        initTableSorter('securities-table');
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

    // --- Security Details Page (Single Chart) ---
    const securityChartCanvas = document.getElementById('primarySecurityChart');
    const securityJsonDataElement = document.getElementById('chartJsonData');

    if (securityChartCanvas && securityJsonDataElement) {
        console.log("Security details page detected. Initializing single chart.");
        try {
            const securityChartData = JSON.parse(securityJsonDataElement.textContent);
            if (securityChartData && securityChartData.primary && securityChartData.primary.labels && securityChartData.primary.datasets) {
                renderSingleSecurityChart(
                    securityChartCanvas.id,
                    securityChartData.primary.labels,
                    securityChartData.primary.datasets,
                    securityChartData.security_id + ' - ' + securityChartData.metric_name
                );
                
                const durationChartCanvas = document.getElementById('durationSecurityChart');
                if(durationChartCanvas && securityChartData.duration && securityChartData.duration.labels && securityChartData.duration.datasets) {
                    renderSingleSecurityChart(
                        durationChartCanvas.id,
                        securityChartData.duration.labels,
                        securityChartData.duration.datasets,
                        securityChartData.security_id + ' - Duration'
                    );
                }

            } else {
                console.warn('Security chart JSON data is incomplete or invalid.', securityChartData);
            }
        } catch (error) {
            console.error('Error parsing security chart data or rendering chart:', error);
        }
    } else {
       // console.log("Security chart canvas or JSON data element not found, skipping single chart rendering.");
    }

    // Add any other global initializations here
});