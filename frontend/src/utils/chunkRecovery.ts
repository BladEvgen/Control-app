const CHUNK_RETRY_STATE_STORAGE_KEY = "__app_chunk_retry_state__";
const CHUNK_LAST_HARD_RELOAD_AT_STORAGE_KEY = "__app_chunk_last_hard_reload_at__";
const CHUNK_RETRY_WINDOW_MS = 45000;
const CHUNK_RETRY_MAX_ATTEMPTS_PER_WINDOW = 2;
const CHUNK_RETRY_MIN_ATTEMPTS_BEFORE_HARD_RELOAD = 1;
const CHUNK_DUPLICATE_ERROR_WINDOW_MS = 2500;
const CHUNK_HARD_RELOAD_COOLDOWN_MS = 45000;
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
  windowStart: number;
  attempts: number;
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

const readRetryState = (now: number): ChunkRetryState => {
  try {
    const raw = sessionStorage.getItem(CHUNK_RETRY_STATE_STORAGE_KEY);
    if (!raw) {
      return { windowStart: now, attempts: 0 };
    }
    const parsed = JSON.parse(raw) as Partial<ChunkRetryState>;
    const windowStart = Number.isFinite(parsed.windowStart)
      ? Number(parsed.windowStart)
      : now;
    const attempts = Number.isFinite(parsed.attempts)
      ? Number(parsed.attempts)
      : 0;
    const lastFingerprint =
      typeof parsed.lastFingerprint === "string"
        ? parsed.lastFingerprint
        : undefined;
    const lastSeenAt = Number.isFinite(parsed.lastSeenAt)
      ? Number(parsed.lastSeenAt)
      : undefined;
    return { windowStart, attempts, lastFingerprint, lastSeenAt };
  } catch {
    return { windowStart: now, attempts: 0 };
  }
};

const writeRetryState = (state: ChunkRetryState): void => {
  try {
    sessionStorage.setItem(CHUNK_RETRY_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore storage errors
  }
};

const hasRecentHardReload = (now: number): boolean => {
  try {
    const raw = sessionStorage.getItem(CHUNK_LAST_HARD_RELOAD_AT_STORAGE_KEY);
    const timestamp = raw ? Number(raw) : NaN;
    return Number.isFinite(timestamp) && now - timestamp < CHUNK_HARD_RELOAD_COOLDOWN_MS;
  } catch {
    return false;
  }
};

export const forceHardReload = (): void => {
  try {
    sessionStorage.setItem(
      CHUNK_LAST_HARD_RELOAD_AT_STORAGE_KEY,
      String(Date.now()),
    );
  } catch {
    // ignore storage errors
  }
  const url = new URL(window.location.href);
  url.searchParams.set("__hard_reload", String(Date.now()));
  window.location.replace(url.toString());
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
  if (hasRecentHardReload(now)) {
    return false;
  }

  const fingerprint = getErrorFingerprint(error);
  const retryState = readRetryState(now);

  if (now - retryState.windowStart > CHUNK_RETRY_WINDOW_MS) {
    retryState.windowStart = now;
    retryState.attempts = 0;
  }

  if (
    retryState.lastFingerprint === fingerprint &&
    Number.isFinite(retryState.lastSeenAt) &&
    now - Number(retryState.lastSeenAt) < CHUNK_DUPLICATE_ERROR_WINDOW_MS
  ) {
    return false;
  }

  if (retryState.attempts >= CHUNK_RETRY_MAX_ATTEMPTS_PER_WINDOW) {
    retryState.lastFingerprint = fingerprint;
    retryState.lastSeenAt = now;
    writeRetryState(retryState);
    return false;
  }

  retryState.attempts += 1;
  retryState.lastFingerprint = fingerprint;
  retryState.lastSeenAt = now;
  writeRetryState(retryState);

  if (retryState.attempts < CHUNK_RETRY_MIN_ATTEMPTS_BEFORE_HARD_RELOAD) {
    return false;
  }

  forceHardReload();
  return true;
};
