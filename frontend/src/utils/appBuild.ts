export type AppBuildMeta = {
  buildId: string;
  builtAtIso: string;
  buildEpochMs: number;
};

export const APP_VERSION_ENDPOINT = "/api/app-version/";
export const APP_VERSION_BROADCAST_STORAGE_KEY = "__app_build_broadcast__";
export const CURRENT_APP_BUILD_META: AppBuildMeta = __APP_BUILD_META__;

export const parseAppBuildMeta = (value: unknown): AppBuildMeta | null => {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Partial<AppBuildMeta>;
  if (
    typeof candidate.buildId !== "string" ||
    candidate.buildId.trim() === "" ||
    typeof candidate.builtAtIso !== "string" ||
    candidate.builtAtIso.trim() === "" ||
    !Number.isFinite(candidate.buildEpochMs)
  ) {
    return null;
  }

  return {
    buildId: candidate.buildId,
    builtAtIso: candidate.builtAtIso,
    buildEpochMs: Number(candidate.buildEpochMs),
  };
};
