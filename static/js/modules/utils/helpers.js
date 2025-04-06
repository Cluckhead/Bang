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