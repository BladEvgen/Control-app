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
        "background-dark": "#2A1A4A",
        "background-darker": "#162D5B",
        "bg-background-gray": "#2D3748",
        "background-dark-purple": "#2A1A4A",
        "text-light": "#F7FAFC",
        "text-dark": "#1A202C",
        "footer-light": "#E2E8F0",
      },
      keyframes: {
        drip: {
          "0%": { height: "20%", backgroundColor: "#162D5B" }, // Цвет header (primary-dark)
          "25%": { height: "40%", backgroundColor: "#1C3375" }, // первый промежуточный оттенок
          "50%": { height: "60%", backgroundColor: "#3B5998" }, // primary-light
          "75%": { height: "80%", backgroundColor: "#2F4B8C" }, // затемнённый оттенок для плавного перехода
          "100%": { height: "100%", backgroundColor: "#F0F4F8" }, // Цвет footer (улучшенная версия footer-light)
        },
        dripDark: {
          "0%": { height: "20%", backgroundColor: "#162D5B" }, // Цвет header (primary-dark)
          "25%": { height: "40%", backgroundColor: "#1C3375" }, // первый промежуточный оттенок
          "50%": { height: "60%", backgroundColor: "#2B3E8C" }, // смещение в сторону синевато-фиолетового оттенка
          "75%": { height: "80%", backgroundColor: "#3A2B7F" }, // усиление фиолетового характера
          "100%": { height: "100%", backgroundColor: "#ebe534" }, // насыщенный фиолетовый для футера
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
