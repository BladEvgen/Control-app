/// <reference types="vite/client" />

type AppBuildMeta = {
  buildId: string;
  builtAtIso: string;
  buildEpochMs: number;
};

declare const __APP_BUILD_META__: AppBuildMeta;
