import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  build: {
    chunkSizeWarningLimit: 1000,
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
