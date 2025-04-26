// This file contains general JavaScript utility functions that can be reused across different modules.
// It helps keep common tasks, like formatting numbers for display, consistent and DRY (Don't Repeat Yourself).

// static/js/modules/utils/helpers.js
// Utility functions

/**
 * Formats a number for display, handling null/undefined.
 * @param {number | null | undefined} value - The number to format.
 * @param {number} [digits=2] - Number of decimal places.
 * @returns {string} Formatted number or 'N/A'.
 */
export function formatNumber(value, digits = 2) {
    if (value === null || typeof value === 'undefined' || isNaN(value)) {
        return 'N/A';
    }
    return Number(value).toFixed(digits);
}

/**
 * Formats a Date object into a YYYY-MM-DD string suitable for date input fields.
 * @param {Date} date - The date object to format.
 * @returns {string} The date string in YYYY-MM-DD format.
 */
export function getIsoDateString(date) {
    if (!(date instanceof Date) || isNaN(date)) {
        console.error("Invalid date passed to getIsoDateString:", date);
        // Return today's date as a fallback
        date = new Date();
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
} 