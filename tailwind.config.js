/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
    './static/css/**/*.css',
  ],
  theme: {
    // --- Overriding default scales ---
    fontSize: {
      'xs': '0.65rem', // Smaller extra-small
      'sm': '0.75rem', // Smaller small
      'base': '0.875rem', // Smaller base (becomes Tailwind's default 'sm')
      'lg': '1rem',    // Smaller large (becomes Tailwind's default 'base')
      'xl': '1.125rem', // Smaller XL
      '2xl': '1.375rem', // Smaller 2XL
      // Add other sizes as needed, keeping them smaller than default
      '3xl': '1.625rem',
      '4xl': '2rem',
      '5xl': '2.5rem',
      // ... etc
    },
    spacing: { // Reduce default spacing - adjust factor (e.g., 0.8) as needed
      px: '1px',
      '0': '0',
      '0.5': '0.1rem',    // Was 0.125rem
      '1': '0.2rem',      // Was 0.25rem
      '1.5': '0.3rem',    // Was 0.375rem
      '2': '0.4rem',      // Was 0.5rem
      '2.5': '0.5rem',    // Was 0.625rem
      '3': '0.6rem',      // Was 0.75rem
      '3.5': '0.7rem',    // Was 0.875rem
      '4': '0.8rem',      // Was 1rem
      '5': '1rem',      // Was 1.25rem
      '6': '1.2rem',      // Was 1.5rem
      '7': '1.4rem',     // Was 1.75rem
      '8': '1.6rem',      // Was 2rem
      '9': '1.8rem',      // Was 2.25rem
      '10': '2rem',       // Was 2.5rem
      '11': '2.2rem',     // Was 2.75rem
      '12': '2.4rem',     // Was 3rem
      '14': '2.8rem',     // Was 3.5rem
      '16': '3.2rem',     // Was 4rem
      '20': '4rem',       // Was 5rem
      // Continue scaling down larger values if needed
      '24': '4.8rem',     // Was 6rem
      '28': '5.6rem',     // Was 7rem
      '32': '6.4rem',     // Was 8rem
      '36': '7.2rem',     // Was 9rem
      '40': '8rem',       // Was 10rem
       // ... and so on
    },
    borderWidth: {
      DEFAULT: '1px', // Ensure default is thin
      '0': '0',
      '2': '2px',
      '4': '4px',
      '8': '8px',
    },
    // --- Extend section for custom additions ---
    extend: {
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
  plugins: [
    require('@tailwindcss/forms'),
  ],
}

