// static/js/modules/ui/securityTableFilter.js
// This module handles client-side filtering for the securities table.

/**
 * Initializes the filtering functionality for the securities table.
 */
export function initSecurityTableFilter() {
    const filterSelects = document.querySelectorAll('.security-filter-select');
    const tableBody = document.getElementById('securities-table-body');

    if (!tableBody || filterSelects.length === 0) {
        console.log("Security table body or filter selects not found. Filtering disabled.");
        return; // Exit if necessary elements aren't present
    }

    // Store all original rows. Use querySelectorAll for robustness.
    const originalRows = Array.from(tableBody.querySelectorAll('tr'));
    if (originalRows.length === 0) {
        console.log("No rows found in the table body.");
        return; // Exit if no data rows
    }

    // Function to get current filter values
    const getCurrentFilters = () => {
        const filters = {};
        filterSelects.forEach(select => {
            if (select.value) { // Only add if a filter is selected (not 'All')
                filters[select.dataset.column] = select.value;
            }
        });
        return filters;
    };

    // Function to perform filtering and update the table
    const applyFilters = () => {
        const currentFilters = getCurrentFilters();
        const filterKeys = Object.keys(currentFilters);

        // Clear current table body content efficiently
        tableBody.innerHTML = ''; 

        originalRows.forEach(row => {
            let matches = true;
            // Get all cells in the current row
            const cells = row.querySelectorAll('td');
            // Assuming the order of cells matches the order of `column_order` from Python
            // We need a way to map filter column names to cell indices
            // Let's get the header names to map column names to indices
            const headerCells = document.querySelectorAll('#securities-table th');
            const columnNameToIndexMap = {};
            headerCells.forEach((th, index) => {
                columnNameToIndexMap[th.textContent.trim()] = index;
            });

            for (const column of filterKeys) {
                const columnIndex = columnNameToIndexMap[column];
                if (columnIndex !== undefined) {
                    const cellValue = cells[columnIndex]?.textContent.trim(); // Use optional chaining
                    // Strict comparison - ensure types match if needed, or use == for type coercion
                    if (cellValue !== currentFilters[column]) {
                        matches = false;
                        break; // No need to check other filters for this row
                    }
                }
                 else {
                      console.warn(`Column "${column}" not found in table header for filtering.`);
                      // Decide how to handle: skip filter, always fail match? Let's skip filter for robustness.
                 }
            }

            if (matches) {
                // Append the row if it matches all active filters
                tableBody.appendChild(row.cloneNode(true)); // Append a clone to avoid issues
            }
        });
        
        // Display a message if no rows match
        if (tableBody.children.length === 0) {
             const noMatchRow = tableBody.insertRow();
             const cell = noMatchRow.insertCell();
             cell.colSpan = headerCells.length; // Span across all columns
             cell.textContent = 'No securities match the current filter criteria.';
             cell.style.textAlign = 'center';
             cell.style.fontStyle = 'italic';
        }
    };

    // Add event listeners to all filter dropdowns
    filterSelects.forEach(select => {
        select.addEventListener('change', applyFilters);
    });

    console.log("Security table filtering initialized.");
} 