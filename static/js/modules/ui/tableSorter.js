// static/js/modules/ui/tableSorter.js
// Purpose: Handles client-side sorting for HTML tables.

/**
 * Initializes sorting functionality for a specified table.
 * @param {string} tableId The ID of the table element to make sortable.
 */
export function initTableSorter(tableId) {
    const table = document.getElementById(tableId);
    if (!table) {
        console.warn(`Table sorter: Table with ID '${tableId}' not found.`);
        return;
    }

    const headers = table.querySelectorAll('thead th.sortable');
    const tbody = table.querySelector('tbody');

    if (!tbody) {
        console.warn(`Table sorter: Table with ID '${tableId}' does not have a tbody.`);
        return;
    }

    headers.forEach(header => {
        header.addEventListener('click', () => {
            // Get column name from data attribute
            const columnName = header.dataset.columnName;
            const currentIsAscending = header.classList.contains('sort-asc');
            const direction = currentIsAscending ? -1 : 1; // -1 for desc, 1 for asc

            // Find the index of the clicked column
            const columnIndex = Array.from(header.parentNode.children).indexOf(header);

            // Remove sorting indicators from other columns
            headers.forEach(h => {
                if (h !== header) {
                  h.classList.remove('sort-asc', 'sort-desc');
                }
            });

            // Set sorting indicator for the current column
            header.classList.toggle('sort-asc', !currentIsAscending);
            header.classList.toggle('sort-desc', currentIsAscending);

            // Sort the rows, passing the column name
            sortRows(tbody, columnIndex, direction, columnName);
        });
    });
}

/**
 * Sorts the rows within a table body.
 * @param {HTMLElement} tbody The table body element containing the rows.
 * @param {number} columnIndex The index of the column to sort by.
 * @param {number} direction 1 for ascending, -1 for descending.
 * @param {string} columnName The name of the column being sorted.
 */
function sortRows(tbody, columnIndex, direction, columnName) {
    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Get the correct comparison function, passing the column name
    const compareFunction = getCompareFunction(rows, columnIndex, columnName);

    // Sort the rows
    rows.sort((rowA, rowB) => {
        const cellA = rowA.children[columnIndex];
        const cellB = rowB.children[columnIndex];
        // Use data-value attribute primarily, fall back to textContent
        const valueA = cellA?.dataset.value ?? cellA?.textContent?.trim() ?? '';
        const valueB = cellB?.dataset.value ?? cellB?.textContent?.trim() ?? '';

        return compareFunction(valueA, valueB) * direction;
    });

    // Re-append sorted rows
    tbody.append(...rows); // More efficient way to re-append
}

/**
 * Determines the appropriate comparison function (numeric or text) based on column content.
 * @param {Array<HTMLElement>} rows Array of table row elements.
 * @param {number} columnIndex The index of the column to check.
 * @param {string} columnName The name of the column being sorted.
 * @returns {function(string, string): number} The comparison function.
 */
function getCompareFunction(rows, columnIndex, columnName) {
    // Check the first few rows (up to 5 data rows) to guess the data type
    let isNumeric = true;
    for (let i = 0; i < Math.min(rows.length, 5); i++) {
        const cell = rows[i].children[columnIndex];
        // Use data-value attribute primarily for checking type
        const value = cell?.dataset.value ?? cell?.textContent?.trim() ?? '';
        // Allow empty strings in numeric columns, but if we find something non-numeric (and not empty), switch to text sort
        if (value !== '' && isNaN(Number(value.replace(/,/g, '')))) {
            isNumeric = false;
            break;
        }
    }

    if (isNumeric) {
        // Check if it's the special column 'Change Z-Score'
        if (columnName === 'Change Z-Score') {
             // Use absolute value for comparison
            return (a, b) => {
                const numA = Math.abs(parseNumber(a));
                const numB = Math.abs(parseNumber(b));
                return numA - numB;
            };
        } else {
            // Standard numeric comparison for other numeric columns
            return (a, b) => {
                const numA = parseNumber(a);
                const numB = parseNumber(b);
                return numA - numB;
            };
        }
    } else {
        // Case-insensitive text comparison
        return (a, b) => a.toLowerCase().localeCompare(b.toLowerCase());
    }
}

/**
 * Helper to parse number, handling empty strings and NaN.
 * Returns -Infinity for values that cannot be parsed as numbers or are empty,
 * ensuring they sort consistently.
 * @param {string} val The string value to parse.
 * @returns {number}
 */
function parseNumber(val) {
    if (val === null || val === undefined || val.trim() === '') {
        return -Infinity; // Treat empty/null/undefined as very small
    }
    const num = Number(val.replace(/,/g, ''));
    // Treat non-numeric as very small. Math.abs(-Infinity) is Infinity, which might be desired
    // when sorting absolute values (non-numbers/empty go to the end when ascending by abs value).
    return isNaN(num) ? -Infinity : num;
} 