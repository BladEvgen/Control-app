// tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        'primary': '#1E3A8A',       // Dark Blue
        'primary-dark': '#162D5B',  // Darker Blue
        'accent': '#805AD5',        // Purple
        'accent-dark': '#6B46C1',   // Dark Purple
        'background-light': '#EDF2F7',  // Light Gray
        'background-dark': '#2D3748',   // Dark Gray
        'text-light': '#F7FAFC',        // Very Light Gray
        'text-dark': '#1A202C',         // Very Dark Gray
        'footer-light': '#E2E8F0',      // Light Gray for Footer
      },
      keyframes: {
        drip: {
          '0%': { height: '0%' },
          '100%': { height: '100%' },
        },
      },
      animation: {
        drip: 'drip 1.5s ease-out forwards',
      },
    },
  },
  plugins: [],
  darkMode: 'class', // Enable dark mode support
};
