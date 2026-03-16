import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";

export default defineConfig(({ mode }) => {
  const withLegacy = mode === "legacy";

  return {
    plugins: [
      react(),
      ...(withLegacy
        ? [
            legacy({
              targets: [
                "defaults",
                "chrome >= 61",
                "ios_saf >= 12",
                "android >= 7",
              ],
              renderLegacyChunks: true,
              modernPolyfills: true,
            }),
          ]
        : []),
    ],
    server: {
      host: "0.0.0.0",
      port: 5173,
    },
    build: {
      emptyOutDir: false,
      cssTarget: withLegacy ? "chrome61" : "esnext",
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks: {
            "chart-vendor": ["chart.js", "react-chartjs-2"],
            "axios-vendor": ["axios"],
            "react-router-vendor": ["react-router-dom"],
            "exceljs-vendor": ["exceljs"],
          },
        },
      },
    },
  };
});
