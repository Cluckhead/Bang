/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
    './static/css/**/*.css',
  ],
  theme: {
    extend: {
      // Custom colors, fonts, and spacing will be added here per the style guide
      fontFamily: {
        sans: ['Inter', 'sans-serif'], // Default body font
        serif: ['Merriweather Sans', 'serif'], // Example serif, maps to Merriweather Sans for headings
        mono: ['Roboto Mono', 'monospace'] // Code/monospace font
      },
      colors: {
        primary: '#E34A33', // Primary Accent
        secondary: '#1F7A8C', // Secondary Accent
        success: '#10B981', // Green 500
        warning: '#F59E0B', // Amber 500
        danger: '#EF4444',  // Red 500
        info: '#3B82F6'     // Blue 500
      }
      // Other extensions like spacing will go here
    },
  },
  plugins: [],
}

