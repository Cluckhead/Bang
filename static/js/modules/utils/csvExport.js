/**
 * CSV Export Utility
 * Provides reusable functions for exporting tables and chart data to CSV format
 * with smart filename generation and logging support.
 */

/**
 * Exports an HTML table to CSV format
 * @param {string} tableId - The ID of the table to export
 * @param {Object} options - Export options
 * @param {string} options.filePrefix - Prefix for the filename (e.g., 'securities', 'attribution')
 * @param {string} options.context - Context/page type (e.g., 'summary', 'details')
 * @param {Object} options.filters - Current filters applied (for filename)
 * @param {string} options.customFilename - Custom filename (overrides auto-generation)
 * @param {boolean} options.includeHeaders - Whether to include table headers (default: true)
 * @param {boolean} options.includeTotals - Whether to include footer totals (default: true)
 * @param {Function} options.onSuccess - Success callback
 * @param {Function} options.onError - Error callback
 */
export function exportTableToCSV(tableId, options = {}) {
    const {
        filePrefix = 'table',
        context = 'data',
        filters = {},
        customFilename = null,
        includeHeaders = true,
        includeTotals = true,
        onSuccess = null,
        onError = null
    } = options;

    try {
        const table = document.getElementById(tableId);
        if (!table) {
            throw new Error(`Table with ID '${tableId}' not found`);
        }

        // Log the export action
        logExportAction('table', tableId, { filePrefix, context, filters });

        // Generate filename
        const filename = customFilename || generateSmartFilename(filePrefix, context, filters);

        // Extract CSV data
        const csvData = extractTableData(table, includeHeaders, includeTotals);

        // Download CSV
        downloadCSV(csvData, filename);

        // Success callback
        if (onSuccess) {
            onSuccess(filename);
        }

    } catch (error) {
        console.error('Error exporting table to CSV:', error);
        if (onError) {
            onError(error);
        }
    }
}

/**
 * Exports chart data to CSV format
 * @param {Object} chartData - Chart data object (from Chart.js or similar)
 * @param {Object} options - Export options (same as exportTableToCSV)
 */
export function exportChartToCSV(chartData, options = {}) {
    const {
        filePrefix = 'chart',
        context = 'data',
        filters = {},
        customFilename = null,
        onSuccess = null,
        onError = null
    } = options;

    try {
        // Log the export action
        logExportAction('chart', 'chart-data', { filePrefix, context, filters });

        // Generate filename
        const filename = customFilename || generateSmartFilename(filePrefix, context, filters);

        // Extract CSV data from chart
        const csvData = extractChartData(chartData);

        // Download CSV
        downloadCSV(csvData, filename);

        // Success callback
        if (onSuccess) {
            onSuccess(filename);
        }

    } catch (error) {
        console.error('Error exporting chart to CSV:', error);
        if (onError) {
            onError(error);
        }
    }
}

/**
 * Extracts data from an HTML table and converts to CSV format
 * @param {HTMLTableElement} table - The table element
 * @param {boolean} includeHeaders - Whether to include headers
 * @param {boolean} includeTotals - Whether to include footer totals
 * @returns {string} CSV data
 */
function extractTableData(table, includeHeaders, includeTotals) {
    const rows = [];
    let totalColumns = 0;

    // Get all rows (thead, tbody, tfoot)
    const allRows = table.querySelectorAll('tr');
    
    // First pass: determine total columns from header row
    if (allRows.length > 0) {
        const headerCells = allRows[0].querySelectorAll('th, td');
        totalColumns = Array.from(headerCells).reduce((acc, cell) => {
            return acc + parseInt(cell.getAttribute('colspan') || '1', 10);
        }, 0);
    }

    // Process each row
    allRows.forEach((row, rowIndex) => {
        const rowParent = row.parentNode.tagName.toLowerCase();
        
        // Skip headers if not included
        if (!includeHeaders && rowParent === 'thead') {
            return;
        }
        
        // Skip totals if not included
        if (!includeTotals && rowParent === 'tfoot') {
            return;
        }

        const cells = row.querySelectorAll('th, td');
        const csvRow = [];

        cells.forEach(cell => {
            const colspan = parseInt(cell.getAttribute('colspan') || '1', 10);
            const rowspan = parseInt(cell.getAttribute('rowspan') || '1', 10);
            
            // Get cell text and clean it
            let cellText = cell.innerText || cell.textContent || '';
            cellText = cellText.replace(/(\r|\n)+/g, ' ').replace(/"/g, '""').trim();
            
            // Add the cell value for colspan expansion
            for (let i = 0; i < colspan; i++) {
                csvRow.push(i === 0 ? `"${cellText}"` : '');
            }
        });

        // Pad row to match total columns
        while (csvRow.length < totalColumns) {
            csvRow.push('');
        }

        rows.push(csvRow.join(','));
    });

    return rows.join('\n');
}

/**
 * Extracts data from chart data object and converts to CSV format
 * @param {Object} chartData - Chart data object
 * @returns {string} CSV data
 */
function extractChartData(chartData) {
    const rows = [];
    
    if (!chartData || !chartData.labels || !chartData.datasets) {
        throw new Error('Invalid chart data structure');
    }

    // Create header row
    const headers = ['Date'];
    chartData.datasets.forEach(dataset => {
        headers.push(`"${dataset.label || 'Data'}"`);
    });
    rows.push(headers.join(','));

    // Create data rows
    chartData.labels.forEach((label, index) => {
        const row = [`"${label}"`];
        chartData.datasets.forEach(dataset => {
            const value = dataset.data[index];
            row.push(value !== undefined && value !== null ? value : '');
        });
        rows.push(row.join(','));
    });

    return rows.join('\n');
}

/**
 * Generates a smart filename based on context and filters
 * @param {string} filePrefix - Base prefix for the file
 * @param {string} context - Context/page type
 * @param {Object} filters - Current filters
 * @returns {string} Generated filename
 */
function generateSmartFilename(filePrefix, context, filters = {}) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const parts = [filePrefix];
    
    if (context && context !== 'data') {
        parts.push(context);
    }
    
    // Add filter values to filename
    Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== 'all' && value !== '') {
            // Clean filter values for filename
            const cleanValue = String(value).replace(/[^a-zA-Z0-9_-]/g, '');
            if (cleanValue) {
                parts.push(cleanValue);
            }
        }
    });
    
    parts.push(timestamp);
    
    return parts.join('_') + '.csv';
}

/**
 * Downloads CSV data as a file
 * @param {string} csvData - CSV data string
 * @param {string} filename - Filename for download
 */
function downloadCSV(csvData, filename) {
    const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.href = url;
        link.download = filename;
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    } else {
        // Fallback for older browsers
        console.warn('CSV download not supported in this browser');
    }
}

/**
 * Logs export actions for monitoring and debugging
 * @param {string} type - Type of export (table, chart)
 * @param {string} elementId - ID of the exported element
 * @param {Object} metadata - Additional metadata
 */
function logExportAction(type, elementId, metadata = {}) {
    try {
        const logData = {
            action: 'csv_export',
            type: type,
            elementId: elementId,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            ...metadata
        };

        // Log to console for debugging
        console.log('CSV Export:', logData);

        // Send to server for logging (optional)
        if (window.location.hostname !== 'localhost') {
            fetch('/api/log-export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(logData)
            }).catch(error => {
                console.warn('Failed to log export action to server:', error);
            });
        }
    } catch (error) {
        console.warn('Failed to log export action:', error);
    }
}

/**
 * Creates a small export button element
 * @param {string} text - Button text (default: 'Export CSV')
 * @param {Function} onClick - Click handler
 * @param {Object} options - Button styling options
 * @returns {HTMLButtonElement} Button element
 */
export function createExportButton(text = 'Export CSV', onClick, options = {}) {
    const {
        size = 'small', // small, medium, large
        style = 'primary', // primary, secondary, outline
        position = 'right', // left, right, center
        className = ''
    } = options;

    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    
    // Base classes
    const baseClasses = [
        'export-csv-btn',
        'rounded-md',
        'font-medium',
        'hover:opacity-90',
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-offset-2',
        'transition-all',
        'duration-200'
    ];
    
    // Size classes
    const sizeClasses = {
        small: ['px-2', 'py-1', 'text-xs'],
        medium: ['px-3', 'py-2', 'text-sm'],
        large: ['px-4', 'py-2', 'text-base']
    };
    
    // Style classes
    const styleClasses = {
        primary: ['bg-primary', 'text-white', 'hover:bg-primary-dark', 'focus:ring-primary'],
        secondary: ['bg-secondary', 'text-white', 'hover:bg-secondary-dark', 'focus:ring-secondary'],
        outline: ['border', 'border-gray-300', 'bg-white', 'text-gray-700', 'hover:bg-gray-50', 'focus:ring-gray-500']
    };
    
    // Combine classes
    const classes = [
        ...baseClasses,
        ...sizeClasses[size] || sizeClasses.small,
        ...styleClasses[style] || styleClasses.primary
    ];
    
    if (className) {
        classes.push(className);
    }
    
    button.className = classes.join(' ');
    
    // Add click handler
    if (onClick) {
        button.addEventListener('click', onClick);
    }
    
    return button;
}

/**
 * Automatically adds export buttons to all tables on the page
 * @param {Object} options - Configuration options
 */
export function addExportButtonsToTables(options = {}) {
    const {
        selector = 'table',
        buttonText = 'Export CSV',
        buttonOptions = {},
        generateOptions = null // Function to generate options for each table
    } = options;

    const tables = document.querySelectorAll(selector);
    
    tables.forEach(table => {
        // Skip if button already exists
        if (table.parentNode.querySelector('.export-csv-btn')) {
            return;
        }
        
        const tableId = table.id;
        if (!tableId) {
            console.warn('Table without ID found, skipping CSV export button');
            return;
        }
        
        // Generate export options for this table
        const exportOptions = generateOptions ? generateOptions(table) : {
            filePrefix: 'table',
            context: 'data'
        };
        
        // Create button
        const button = createExportButton(
            buttonText,
            () => exportTableToCSV(tableId, exportOptions),
            buttonOptions
        );
        
        // Add button to table container
        const container = table.parentNode;
        if (container.classList.contains('overflow-x-auto')) {
            // Add to parent of scroll container
            container.parentNode.insertBefore(button, container);
        } else {
            container.insertBefore(button, table);
        }
    });
}

/**
 * Utility function to get current page context and filters
 * @returns {Object} Context and filters object
 */
export function getCurrentPageContext() {
    const path = window.location.pathname;
    const searchParams = new URLSearchParams(window.location.search);
    
    // Extract context from URL path
    let context = 'data';
    let filePrefix = 'export';
    
    if (path.includes('/securities')) {
        filePrefix = 'securities';
        context = path.includes('/summary') ? 'summary' : 'details';
    } else if (path.includes('/attribution')) {
        filePrefix = 'attribution';
        context = path.includes('/summary') ? 'summary' : 'details';
    } else if (path.includes('/funds')) {
        filePrefix = 'funds';
        context = path.includes('/details') ? 'details' : 'summary';
    } else if (path.includes('/metrics')) {
        filePrefix = 'metrics';
        context = 'details';
    } else if (path.includes('/comparison')) {
        filePrefix = 'comparison';
        context = 'summary';
    }
    
    // Extract common filters from URL parameters
    const filters = {};
    ['fund', 'metric', 'level', 'start_date', 'end_date', 'characteristic'].forEach(key => {
        const value = searchParams.get(key);
        if (value) {
            filters[key] = value;
        }
    });
    
    return { context, filePrefix, filters };
}