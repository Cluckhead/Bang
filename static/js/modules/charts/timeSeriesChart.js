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
        console.error(`Failed to get 2D context for canvas ID: ${canvasId}`);
        return; // Exit if canvas context is not available
    }

    // --- Prepare Chart Title --- 
    let titleSuffix = maxZScore !== null ? `(Max Spread Z: ${maxZScore.toFixed(2)})` : '(Z-Score N/A)';
    if (isMissingLatest) {
        titleSuffix = "(MISSING LATEST DATA)";
    }
    const chartTitle = `${metricName} for ${fundCode} ${titleSuffix}`;

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
                    // Optional: Customize tooltip further if needed
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

    // --- Create Chart Instance --- 
    // Check if a chart instance already exists on the canvas and destroy it
    let existingChart = Chart.getChart(canvasId);
    if (existingChart) {
        existingChart.destroy();
    }
    new Chart(ctx, config);
    console.log(`Chart created for ${fundCode} on ${canvasId}`);

} 