// static/js/main.js
// Application entry point

import { renderChartsAndTables } from './modules/ui/chartRenderer.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    const dataElement = document.getElementById('chartData');
    if (!dataElement) {
        console.error('Chart data element not found!');
        return;
    }

    try {
        const chartsData = JSON.parse(dataElement.textContent);
        console.log("Parsed Chart Data:", chartsData);

        const chartsArea = document.getElementById('chartsArea');
        if (!chartsArea) {
            console.error('Charts area element not found!');
            return;
        }

        const metricNameElement = document.querySelector('h1');
        const metricName = metricNameElement ? metricNameElement.textContent.replace(' Check', '') : 'Metric';
        const latestDate = document.querySelector('main p strong').textContent;

        let fundColNamesList = [];
        let benchmarkColName = 'Benchmark Value';
        const fundCodes = Object.keys(chartsData);

        if (fundCodes.length > 0) {
            const firstFundCode = fundCodes[0];
            const firstFundData = chartsData[firstFundCode];
            if (firstFundData && firstFundData.fund_column_names) {
                fundColNamesList = firstFundData.fund_column_names;
            }
            if (firstFundData && firstFundData.datasets && firstFundData.datasets.length > 0) {
                benchmarkColName = firstFundData.datasets[firstFundData.datasets.length - 1].label;
            }
        }
        console.log("Fund Columns:", fundColNamesList);
        console.log("Benchmark Column:", benchmarkColName);

        renderChartsAndTables(chartsArea, chartsData, metricName, latestDate, fundColNamesList, benchmarkColName);

    } catch (error) {
        console.error('Error parsing chart data or rendering charts:', error);
        const chartsArea = document.getElementById('chartsArea');
        if (chartsArea) {
            chartsArea.innerHTML = '<p class="text-danger">Error loading chart data.</p>';
        }
    }
});