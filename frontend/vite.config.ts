import { defineConfig, type Plugin } from "vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";

type AppBuildMeta = {
  buildId: string;
  builtAtIso: string;
  buildEpochMs: number;
};

const padNumber = (value: number, size = 2): string =>
  String(value).padStart(size, "0");

const formatLocalBuildId = (date: Date): string =>
  [
    `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`,
    `${padNumber(date.getHours())}-${padNumber(date.getMinutes())}-${padNumber(date.getSeconds())}_${padNumber(date.getMilliseconds(), 3)}`,
  ].join("_");

const resolveBuildMeta = (): AppBuildMeta => {
  const envEpochMs = Number(process.env.APP_BUILD_EPOCH_MS);
  const date = Number.isFinite(envEpochMs) ? new Date(envEpochMs) : new Date();
  const builtAtIso =
    typeof process.env.APP_BUILD_TIME_ISO === "string" &&
    process.env.APP_BUILD_TIME_ISO.trim() !== ""
      ? process.env.APP_BUILD_TIME_ISO
      : date.toISOString();
  const buildId =
    typeof process.env.APP_BUILD_ID === "string" &&
    process.env.APP_BUILD_ID.trim() !== ""
      ? process.env.APP_BUILD_ID
      : formatLocalBuildId(date);

  return {
    buildId,
    builtAtIso,
    buildEpochMs: date.getTime(),
  };
};

const buildMetadataPlugin = (buildMeta: AppBuildMeta): Plugin => ({
  name: "app-build-metadata",
  apply: "build",
  generateBundle() {
    this.emitFile({
      type: "asset",
      fileName: "app-version.json",
      source: `${JSON.stringify(buildMeta, null, 2)}\n`,
    });
  },
});

export default defineConfig(() => {
  const buildMeta = resolveBuildMeta();

  return {
    define: {
      __APP_BUILD_META__: JSON.stringify(buildMeta),
    },
    plugins: [tailwindcss(), react(), buildMetadataPlugin(buildMeta)],
    server: {
      host: "0.0.0.0",
      port: 5173,
    },
    build: {
      emptyOutDir: false,
      cssTarget: "esnext",
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
