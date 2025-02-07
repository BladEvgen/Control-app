import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
          "chart-vendor": ["chart.js", "react-chartjs-2"],
          "axios-vendor": ["axios"],
          "react-router-vendor": ["react-router-dom"],
          "exceljs-vendor": ["exceljs"],
        },
      },
    },
  },
});
