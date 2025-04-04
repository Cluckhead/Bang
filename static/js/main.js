// static/js/main.js
// Application entry point

import { renderChartsAndTables, renderSingleSecurityChart } from './modules/ui/chartRenderer.js';
import { initSecurityTableFilter } from './modules/ui/securityTableFilter.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // --- Try to Initialize Charts (for metric pages) ---
    const chartDataElement = document.getElementById('chartData');
    if (chartDataElement) {
        console.log("Chart data element found. Attempting chart rendering...")
        try {
            const chartsData = JSON.parse(chartDataElement.textContent);
            console.log("Parsed Chart Data:", chartsData);

            const chartsArea = document.getElementById('chartsArea');
            if (!chartsArea) {
                console.error('Charts area element not found!');
            } else {
                const metricNameElement = document.querySelector('h1');
                const metricName = metricNameElement ? metricNameElement.textContent.replace(' Check', '') : 'Metric';
                // Safely get latest date - might need adjustment based on actual structure
                const latestDateElement = document.querySelector('main p strong');
                const latestDate = latestDateElement ? latestDateElement.textContent : 'N/A';

                let fundColNamesList = [];
                let benchmarkColName = 'Benchmark Value'; // Default
                const fundCodes = Object.keys(chartsData);

                if (fundCodes.length > 0) {
                    const firstFundCode = fundCodes[0];
                    const firstFundData = chartsData[firstFundCode];
                    if (firstFundData && firstFundData.fund_column_names) {
                        fundColNamesList = firstFundData.fund_column_names;
                    }
                    // Adjust benchmark name finding if structure differs
                    if (firstFundData && firstFundData.benchmark_column_name) {
                        benchmarkColName = firstFundData.benchmark_column_name;
                    } else if (firstFundData && firstFundData.datasets && firstFundData.datasets.length > 0) {
                         // Fallback: try to get from datasets if key is missing
                         const benchmarkDataset = firstFundData.datasets.find(ds => ds.label && ds.label.toLowerCase().includes('benchmark'));
                         if (benchmarkDataset) benchmarkColName = benchmarkDataset.label;
                    }
                }
                console.log("Fund Columns:", fundColNamesList);
                console.log("Benchmark Column:", benchmarkColName);

                renderChartsAndTables(chartsArea, chartsData, metricName, latestDate, fundColNamesList, benchmarkColName);
            }

        } catch (error) {
            console.error('Error parsing chart data or rendering charts:', error);
            const chartsArea = document.getElementById('chartsArea');
            if (chartsArea) {
                chartsArea.innerHTML = '<p class="text-danger">Error loading chart data.</p>';
            }
        }
    } else {
        console.log("Chart data element not found (Expected on non-metric pages).");
        // No return here - allow script to continue
    }

    // --- Try to Initialize Security Table Filter (for securities page) ---
    const tableElement = document.getElementById('securities-table'); 
    console.log("Checking for securities table element:", tableElement); 
    if (tableElement) { 
        console.log("Securities table element found. Initializing filter...");
        initSecurityTableFilter();
    } else {
        console.log("Securities table element NOT found (Expected on non-securities pages).");
    }
    
    // --- Try to Initialize Single Security Chart (for security details page) ---
    const singleChartCanvas = document.getElementById('securityChart');
    const singleChartDataElement = document.getElementById('chartJsonData');
    console.log("Checking for single security chart canvas:", singleChartCanvas);
    console.log("Checking for single security chart data:", singleChartDataElement);
    
    if (singleChartCanvas && singleChartDataElement) {
        console.log("Single security chart elements found. Initializing chart...");
        try {
            const chartData = JSON.parse(singleChartDataElement.textContent);
            // Extract securityId and metricName - might need to pass these differently or get from URL/DOM
            const pageTitle = document.title;
            let securityId = 'Unknown';
            let metricName = 'Unknown';
            const titleMatch = pageTitle.match(/Security Details: (.*?) - (.*)/);
            if (titleMatch && titleMatch.length >= 3) {
                 securityId = titleMatch[1];
                 metricName = titleMatch[2];
            }
            
            renderSingleSecurityChart(singleChartCanvas.id, chartData, securityId, metricName);
        } catch (error) {
            console.error('Error parsing or rendering single security chart:', error);
            singleChartCanvas.parentElement.innerHTML = '<p class="text-danger">Error loading chart.</p>';
        }
    } else {
         console.log("Single security chart elements NOT found (Expected on other pages).");
    }

    // Add any other global initializations here
});