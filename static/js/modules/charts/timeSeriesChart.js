// This file contains the specific logic for creating and configuring time-series line charts
// using the Chart.js library. It's designed to be reusable for generating consistent charts
// across different metrics and funds.

// static/js/modules/charts/timeSeriesChart.js
// Encapsulates Chart.js configuration and rendering for multiple time series datasets

/**
 * Creates and renders a time series chart using Chart.js.
 * @param {string} canvasId - The ID of the canvas element.
 * @param {object} chartData - Data object containing labels, multiple datasets, metrics.
 * @param {string} metricName - Name of the overall metric (e.g., Duration).
 * @param {string} fundCode - Code of the specific fund.
 * @param {number | null} maxZScore - The maximum absolute Z-score for this fund (used in title).
 * @param {boolean} isMissingLatest - Flag indicating if the latest point is missing for any spread.
 */
export function createTimeSeriesChart(canvasId, chartData, metricName, fundCode, maxZScore, isMissingLatest) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    if (!ctx) {
        console.error(`[createTimeSeriesChart] Failed to get 2D context for canvas ID: ${canvasId}`);
        return; // Exit if canvas context is not available
    }

    // --- Prepare Chart Title (Adjusted for different contexts) --- 
    let chartTitle = metricName; // Default to just the metric name
    if (fundCode) { // If fundCode is provided (called from metric page)
        let titleSuffix = maxZScore !== null ? `(Max Spread Z: ${maxZScore.toFixed(2)})` : '(Z-Score N/A)';
        if (isMissingLatest) {
            titleSuffix = "(MISSING LATEST DATA)";
        }
        chartTitle = `${metricName} for ${fundCode} ${titleSuffix}`; 
    }
    // If fundCode is null (called from fund page), title remains just metricName
    console.log(`[createTimeSeriesChart] Using chart title: "${chartTitle}" for canvas ${canvasId}`);

    // --- Prepare Chart Data & Styling --- 
    const datasets = chartData.datasets.map((ds, index) => {
        const isBenchmark = ds.label.includes('Benchmark'); // Basic check, refine if needed
        const isLastDataset = index === chartData.datasets.length - 1; // Check if it's the benchmark dataset based on order from app.py

        return {
            ...ds,
            // Style points - highlight last point for non-benchmark lines
            pointRadius: (context) => {
                const isLastPoint = context.dataIndex === (ds.data.length - 1);
                // Only show large radius for last point of non-benchmark datasets
                return isLastPoint && !isLastDataset ? 6 : 0;
            },
            pointHoverRadius: (context) => {
                const isLastPoint = context.dataIndex === (ds.data.length - 1);
                return isLastPoint && !isLastDataset ? 8 : 5;
            },
            pointBackgroundColor: isLastDataset ? 'darkgrey' : ds.borderColor, // Use border color for fund points, grey for benchmark
            borderWidth: isLastDataset ? 2 : 1.5, // Slightly thicker benchmark line
        };
    });


    // --- Chart Configuration --- 
    const config = {
        type: 'line',
        data: {
            labels: chartData.labels, // Dates as strings
            datasets: datasets // Now includes multiple fund series + benchmark
        },
        options: {
            responsive: true,
            maintainAspectRatio: false, 
            plugins: {
                title: { display: true, text: chartTitle, font: { size: 16 } },
                legend: { position: 'top' },
                tooltip: { 
                    mode: 'index', 
                    intersect: false, 
                }
            },
            hover: { mode: 'nearest', intersect: true },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day',
                        tooltipFormat: 'MMM dd, yyyy',
                        displayFormats: { day: 'MMM dd', week: 'MMM dd yyyy', month: 'MMM yyyy' }
                    },
                    title: { display: true, text: 'Date' }
                },
                y: {
                    display: true,
                    title: { display: true, text: metricName },
                    // Dynamic scaling based on *all* datasets
                    suggestedMin: Math.min(...datasets.flatMap(ds => ds.data.filter(d => d !== null && !isNaN(d)))),
                    suggestedMax: Math.max(...datasets.flatMap(ds => ds.data.filter(d => d !== null && !isNaN(d))))
                }
            }
        }
    };

    // --- Create Chart Instance (with Error Handling) --- 
    try {
        // Check if a chart instance already exists on the canvas and destroy it
        let existingChart = Chart.getChart(canvasId);
        if (existingChart) {
            console.log(`[createTimeSeriesChart] Destroying existing chart on canvas ${canvasId}`);
            existingChart.destroy();
        }
        
        // Attempt to create the new chart
        console.log(`[createTimeSeriesChart] Attempting to create new Chart on canvas ${canvasId}`);
        new Chart(ctx, config);
        
        // Log success *after* instantiation
        console.log(`[createTimeSeriesChart] Successfully created chart for "${chartTitle}" on ${canvasId}`);

    } catch (error) {
        // Log any error during chart instantiation
        console.error(`[createTimeSeriesChart] Error creating chart on canvas ${canvasId} for "${chartTitle}":`, error);
        // Optionally display an error message in the canvas container
        const errorP = document.createElement('p');
        errorP.textContent = `Error rendering chart: ${error.message}`;
        errorP.className = 'text-danger';
        // Attempt to add error message to parent, replacing canvas if needed
        const canvasElement = document.getElementById(canvasId);
        if (canvasElement && canvasElement.parentElement) {
            canvasElement.parentElement.appendChild(errorP);
            canvasElement.style.display = 'none'; // Hide broken canvas
        }    
    }
} 