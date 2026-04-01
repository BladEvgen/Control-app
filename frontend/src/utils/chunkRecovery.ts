import { guardedAutoReload, forceHardReload } from "./appAutoReload";

const CHUNK_RETRY_STATE_STORAGE_KEY = "__app_chunk_retry_state__";
const CHUNK_DUPLICATE_ERROR_WINDOW_MS = 2500;
const CHUNK_MIN_UPTIME_BEFORE_HARD_RELOAD_MS = 1500;

const CHUNK_ERROR_PATTERNS: RegExp[] = [
  /ChunkLoadError/i,
  /Loading chunk [\w-]+ failed/i,
  /Failed to fetch dynamically imported module/i,
  /Error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /Failed to load module script/i,
];

const ABORT_LIKE_ERROR_PATTERNS: RegExp[] = [
  /\bAbortError\b/i,
  /\bThe operation was aborted\b/i,
  /\bThe user aborted a request\b/i,
  /\bNS_BINDING_ABORTED\b/i,
];

type ChunkRetryState = {
  lastFingerprint?: string;
  lastSeenAt?: number;
};

const toErrorText = (error: unknown): string => {
  if (typeof error === "string") return error;
  if (error instanceof Error) return `${error.name}: ${error.message}`;
  if (error && typeof error === "object") {
    const maybeMessage = (error as { message?: unknown }).message;
    if (typeof maybeMessage === "string") return maybeMessage;
    const nested = (error as { error?: unknown }).error;
    if (nested) return toErrorText(nested);
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }
  return String(error);
};

export const isChunkLoadError = (error: unknown): boolean => {
  const text = toErrorText(error);
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(text));
};

export const isAbortLikeLoadError = (error: unknown): boolean => {
  const text = toErrorText(error);
  return ABORT_LIKE_ERROR_PATTERNS.some((pattern) => pattern.test(text));
};

const getErrorFingerprint = (error: unknown): string => {
  return toErrorText(error).trim().slice(0, 180);
};

const readRetryState = (): ChunkRetryState => {
  try {
    const raw = sessionStorage.getItem(CHUNK_RETRY_STATE_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Partial<ChunkRetryState>;
    const lastFingerprint =
      typeof parsed.lastFingerprint === "string"
        ? parsed.lastFingerprint
        : undefined;
    const lastSeenAt = Number.isFinite(parsed.lastSeenAt)
      ? Number(parsed.lastSeenAt)
      : undefined;
    return { lastFingerprint, lastSeenAt };
  } catch {
    return {};
  }
};

const writeRetryState = (state: ChunkRetryState): void => {
  try {
    sessionStorage.setItem(CHUNK_RETRY_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore storage errors
  }
};

export const tryRecoverChunkLoadError = (error: unknown): boolean => {
  if (isAbortLikeLoadError(error)) return false;
  if (!isChunkLoadError(error)) return false;
  if (typeof document !== "undefined" && document.visibilityState === "hidden") {
    return false;
  }
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return false;
  }
  if (
    typeof performance !== "undefined" &&
    performance.now() < CHUNK_MIN_UPTIME_BEFORE_HARD_RELOAD_MS
  ) {
    return false;
  }

  const now = Date.now();
  const fingerprint = getErrorFingerprint(error);
  const retryState = readRetryState();

  if (
    retryState.lastFingerprint === fingerprint &&
    Number.isFinite(retryState.lastSeenAt) &&
    now - Number(retryState.lastSeenAt) < CHUNK_DUPLICATE_ERROR_WINDOW_MS
  ) {
    return false;
  }

  retryState.lastFingerprint = fingerprint;
  retryState.lastSeenAt = now;
  writeRetryState(retryState);
  return guardedAutoReload({
    targetBuildId: `chunk:${fingerprint}`,
    reason: "chunk-load-error",
  });
};

export { forceHardReload };
