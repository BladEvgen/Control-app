import {
  APP_VERSION_BROADCAST_STORAGE_KEY,
  APP_VERSION_ENDPOINT,
  CURRENT_APP_BUILD_META,
  parseAppBuildMeta,
  type AppBuildMeta,
} from "./appBuild";
import { guardedAutoReload, reconcilePendingAutoReload } from "./appAutoReload";
import { tryRecoverChunkLoadError } from "./chunkRecovery";

const VERSION_CHECK_INTERVAL_MS = 60_000;

let guardStarted = false;
let inFlightCheck: Promise<void> | null = null;
let latestKnownBuildMeta: AppBuildMeta | null = null;

const rememberLatestBuild = (buildMeta: AppBuildMeta): void => {
  latestKnownBuildMeta = buildMeta;
};

const broadcastLatestBuild = (buildMeta: AppBuildMeta): void => {
  try {
    localStorage.setItem(
      APP_VERSION_BROADCAST_STORAGE_KEY,
      JSON.stringify(buildMeta),
    );
  } catch {
    // ignore storage issues
  }
};

const fetchLatestBuildMeta = async (): Promise<AppBuildMeta | null> => {
  try {
    const response = await fetch(
      `${APP_VERSION_ENDPOINT}?ts=${Date.now()}`,
      {
        cache: "no-store",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Cache-Control": "no-cache",
        },
      },
    );
    if (!response.ok) {
      return null;
    }

    const payload = parseAppBuildMeta(await response.json());
    if (!payload) {
      return null;
    }

    rememberLatestBuild(payload);
    return payload;
  } catch {
    return null;
  }
};

const maybeReloadToBuild = (
  buildMeta: AppBuildMeta,
  reason: string,
  { shouldBroadcast = true }: { shouldBroadcast?: boolean } = {},
): boolean => {
  if (buildMeta.buildId === CURRENT_APP_BUILD_META.buildId) {
    return false;
  }

  rememberLatestBuild(buildMeta);
  if (shouldBroadcast) {
    broadcastLatestBuild(buildMeta);
  }
  return guardedAutoReload({
    targetBuildId: buildMeta.buildId,
    reason,
  });
};

const runVersionCheck = async (reason: string): Promise<void> => {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return;
  }

  const latestBuildMeta = await fetchLatestBuildMeta();
  if (!latestBuildMeta) {
    return;
  }

  maybeReloadToBuild(latestBuildMeta, `app-version:${reason}`);
};

const enqueueVersionCheck = (reason: string): Promise<void> => {
  if (inFlightCheck) {
    return inFlightCheck;
  }

  inFlightCheck = runVersionCheck(reason).finally(() => {
    inFlightCheck = null;
  });
  return inFlightCheck;
};

export const requestAppVersionCheck = (reason = "manual"): Promise<void> => {
  return enqueueVersionCheck(reason);
};

export const handleBuildSkewDetected = async (
  reason: string,
  cause?: unknown,
): Promise<boolean> => {
  if (
    latestKnownBuildMeta &&
    latestKnownBuildMeta.buildId !== CURRENT_APP_BUILD_META.buildId
  ) {
    return maybeReloadToBuild(latestKnownBuildMeta, reason);
  }

  const latestBuildMeta = await fetchLatestBuildMeta();
  if (
    latestBuildMeta &&
    latestBuildMeta.buildId !== CURRENT_APP_BUILD_META.buildId
  ) {
    return maybeReloadToBuild(latestBuildMeta, reason);
  }

  if (cause !== undefined) {
    return tryRecoverChunkLoadError(cause);
  }
  return false;
};

export const startAppVersionGuard = (): void => {
  if (guardStarted) return;
  guardStarted = true;

  reconcilePendingAutoReload();
  void requestAppVersionCheck("startup");

  window.addEventListener("pageshow", () => {
    if (document.visibilityState === "visible") {
      void requestAppVersionCheck("pageshow");
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      void requestAppVersionCheck("visibilitychange");
    }
  });

  window.addEventListener("focus", () => {
    if (document.visibilityState === "visible") {
      void requestAppVersionCheck("focus");
    }
  });

  window.addEventListener("online", () => {
    void requestAppVersionCheck("online");
  });

  window.addEventListener("storage", (event) => {
    if (
      event.key !== APP_VERSION_BROADCAST_STORAGE_KEY ||
      typeof event.newValue !== "string"
    ) {
      return;
    }

    try {
      const payload = parseAppBuildMeta(JSON.parse(event.newValue));
      if (!payload) return;
      maybeReloadToBuild(payload, "cross-tab", { shouldBroadcast: false });
    } catch {
      // ignore malformed storage payloads
    }
  });

  window.setInterval(() => {
    if (document.visibilityState === "visible") {
      void requestAppVersionCheck("interval");
    }
  }, VERSION_CHECK_INTERVAL_MS);
};
