/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Poppins", "Plus Jakarta Sans", "system-ui", "sans-serif"],
      },
      colors: {
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
        surface: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
        },
        text: { light: "#f8fafc", dark: "#0f172a" },
        background: { light: "#f8fafc", dark: "#0f172a" },
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.05), 0 1px 2px -1px rgb(0 0 0 / 0.05)",
        "card-hover": "0 12px 28px -8px rgb(0 0 0 / 0.08), 0 4px 12px -4px rgb(0 0 0 / 0.04)",
        "card-lg": "0 20px 40px -12px rgb(0 0 0 / 0.08), 0 8px 16px -8px rgb(0 0 0 / 0.04)",
        header: "0 1px 0 0 rgb(255 255 255 / 0.06)",
      },
      animation: {
        enter: "enter 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards",
        "enter-slow": "enter 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards",
        "dropdown-in": "dropdownIn 0.2s ease-out forwards",
      },
      keyframes: {
        enter: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        dropdownIn: {
          "0%": { opacity: "0", transform: "scale(0.96) translateY(-4px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
      },
      transitionDuration: { 200: "200ms", 250: "250ms", 300: "300ms" },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
