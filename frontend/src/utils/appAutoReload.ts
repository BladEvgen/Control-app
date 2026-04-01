import { CURRENT_APP_BUILD_META } from "./appBuild";
import { isNavigationTransitionPending } from "./pageLifecycle";

const AUTO_RELOAD_STATE_STORAGE_KEY = "__app_auto_reload_state__";
const HARD_RELOAD_QUERY_PARAM = "__hard_reload";
const HARD_RELOAD_TARGET_QUERY_PARAM = "__hard_reload_target";
const AUTO_RELOAD_VISUAL_DELAY_MS = 260;

type AutoReloadState = {
  targetBuildId: string;
  attempts: number;
  lastAttemptAt: number;
  awaitingTargetOnNextBoot: boolean;
  blocked: boolean;
};

const isBrowser = typeof window !== "undefined";

const normalizeTargetBuildId = (
  targetBuildId: string | undefined,
  reason: string,
): string => {
  const normalized = targetBuildId?.trim();
  return normalized && normalized.length > 0
    ? normalized
    : `fallback:${CURRENT_APP_BUILD_META.buildId}:${reason}`;
};

const readAutoReloadState = (): AutoReloadState | null => {
  if (!isBrowser) return null;

  try {
    const raw = sessionStorage.getItem(AUTO_RELOAD_STATE_STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<AutoReloadState>;
    if (
      typeof parsed.targetBuildId !== "string" ||
      parsed.targetBuildId.trim() === "" ||
      !Number.isFinite(parsed.attempts) ||
      !Number.isFinite(parsed.lastAttemptAt) ||
      typeof parsed.awaitingTargetOnNextBoot !== "boolean" ||
      typeof parsed.blocked !== "boolean"
    ) {
      return null;
    }

    return {
      targetBuildId: parsed.targetBuildId,
      attempts: Number(parsed.attempts),
      lastAttemptAt: Number(parsed.lastAttemptAt),
      awaitingTargetOnNextBoot: parsed.awaitingTargetOnNextBoot,
      blocked: parsed.blocked,
    };
  } catch {
    return null;
  }
};

const writeAutoReloadState = (state: AutoReloadState): void => {
  if (!isBrowser) return;
  try {
    sessionStorage.setItem(AUTO_RELOAD_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore storage issues
  }
};

const clearAutoReloadState = (): void => {
  if (!isBrowser) return;
  try {
    sessionStorage.removeItem(AUTO_RELOAD_STATE_STORAGE_KEY);
  } catch {
    // ignore storage issues
  }
};

export const clearHardReloadParams = (): void => {
  if (!isBrowser) return;

  try {
    const url = new URL(window.location.href);
    let changed = false;

    if (url.searchParams.has(HARD_RELOAD_QUERY_PARAM)) {
      url.searchParams.delete(HARD_RELOAD_QUERY_PARAM);
      changed = true;
    }
    if (url.searchParams.has(HARD_RELOAD_TARGET_QUERY_PARAM)) {
      url.searchParams.delete(HARD_RELOAD_TARGET_QUERY_PARAM);
      changed = true;
    }
    if (!changed) return;

    const next =
      `${url.pathname}${url.search ? url.search : ""}${url.hash ? url.hash : ""}` ||
      "/";
    window.history.replaceState(window.history.state, "", next);
  } catch {
    // ignore URL/history issues
  }
};

export const reconcilePendingAutoReload = (): void => {
  const state = readAutoReloadState();
  if (!state?.awaitingTargetOnNextBoot) return;

  if (CURRENT_APP_BUILD_META.buildId === state.targetBuildId) {
    clearAutoReloadState();
    return;
  }

  writeAutoReloadState({
    ...state,
    awaitingTargetOnNextBoot: false,
    blocked: true,
  });
};

export const forceHardReload = (targetBuildId?: string): void => {
  if (!isBrowser) return;

  const url = new URL(window.location.href);
  url.searchParams.set(HARD_RELOAD_QUERY_PARAM, String(Date.now()));

  if (targetBuildId) {
    url.searchParams.set(HARD_RELOAD_TARGET_QUERY_PARAM, targetBuildId);
  } else {
    url.searchParams.delete(HARD_RELOAD_TARGET_QUERY_PARAM);
  }

  window.location.replace(url.toString());
};

export const guardedAutoReload = ({
  targetBuildId,
  reason,
  message = "Обновляем приложение до последнего релиза…",
}: {
  targetBuildId?: string;
  reason: string;
  message?: string;
}): boolean => {
  if (!isBrowser) return false;
  if (isNavigationTransitionPending()) return false;

  const normalizedTargetBuildId = normalizeTargetBuildId(targetBuildId, reason);
  const currentState = readAutoReloadState();

  if (
    currentState &&
    currentState.targetBuildId === normalizedTargetBuildId &&
    (currentState.awaitingTargetOnNextBoot ||
      currentState.blocked ||
      currentState.attempts >= 1)
  ) {
    return false;
  }

  writeAutoReloadState({
    targetBuildId: normalizedTargetBuildId,
    attempts: 1,
    lastAttemptAt: Date.now(),
    awaitingTargetOnNextBoot: true,
    blocked: false,
  });

  if (document.visibilityState === "hidden") {
    forceHardReload(normalizedTargetBuildId);
    return true;
  }

  window.__APP_BOOT__?.showReloading?.(message);
  window.setTimeout(() => {
    forceHardReload(normalizedTargetBuildId);
  }, AUTO_RELOAD_VISUAL_DELAY_MS);
  return true;
};
