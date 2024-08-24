/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#1E3A8A",
        "primary-dark": "#162D5B",
        "primary-mid": "#1C3375",
        "primary-light": "#3B5998",
        accent: "#805AD5",
        "accent-dark": "#6B46C1",
        "accent-mid": "#734BBF",
        "accent-light": "#9D7FEA",
        "background-light": "#EDF2F7",
        "background-dark": "#2D3748",
        "background-darker": "#1A202C",
        "text-light": "#F7FAFC",
        "text-dark": "#1A202C",
        "footer-light": "#E2E8F0",
      },
      keyframes: {
        drip: {
          "0%": { height: "0%", backgroundColor: "#1E3A8A" },
          "20%": { height: "20%", backgroundColor: "#1C3375" },
          "40%": { height: "40%", backgroundColor: "#3B5998" },
          "60%": { height: "60%", backgroundColor: "#162D5B" },
          "80%": { height: "80%", backgroundColor: "#1C3375" },
          "100%": { height: "100%", backgroundColor: "#1E3A8A" },
        },
        dripDark: {
          "0%": { height: "0%", backgroundColor: "#2D3748" },
          "20%": { height: "20%", backgroundColor: "#1A202C" },
          "40%": { height: "40%", backgroundColor: "#162D5B" },
          "60%": { height: "60%", backgroundColor: "#1C3375" },
          "80%": { height: "80%", backgroundColor: "#162D5B" },
          "100%": { height: "100%", backgroundColor: "#2D3748" },
        },
        fadeIn: {
          "0%": { opacity: 0 },
          "100%": { opacity: 1 },
        },
      },
      animation: {
        drip: "drip 1.2s ease-out forwards",
        dripDark: "dripDark 1.2s ease-out forwards",
        fadeIn: "fadeIn 1.3s ease-in forwards",
      },
    },
  },
  plugins: [],
  darkMode: "class",
};
