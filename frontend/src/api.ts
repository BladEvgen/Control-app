import { addPrefix } from "./RouterUtils";
import axios, { AxiosResponse, isAxiosError } from "axios";
import { apiUrl, isDebug } from "../apiConfig";
import { jwtCookieMaxAgeSeconds } from "./authSession/jwtCookieMaxAge.ts";

let _prodWarningCount = 0;
let _prodWarningShown = false;
let _prodWarningReportDone = false;

const log = {
  info: (...args: unknown[]) => {
    if (isDebug) {
      console.log(`%cINFO:`, "color: green; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  warn: (...args: unknown[]) => {
    if (isDebug) {
      console.log(`%cWARN:`, "color: orange; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  error: (...args: unknown[]) => {
    if (isDebug) {
      console.error(`%cERROR:`, "color: red; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  prodWarning: () => {
    _prodWarningCount += 1;
    if (!_prodWarningShown) {
      _prodWarningShown = true;
      console.warn(
        "%cWARNING:",
        "color: yellow; font-weight: bold; font-size: 16px;",
        "This function is intended for developers. If you're an ordinary user, it's better to close this.",
      );
      const reportCount = () => {
        if (_prodWarningReportDone) return;
        _prodWarningReportDone = true;
        if (_prodWarningCount > 0) {
          console.warn(
            "[dev log] Suppressed",
            _prodWarningCount,
            "developer-only message(s) on this page.",
          );
        }
      };
      window.addEventListener("beforeunload", reportCount);
      setTimeout(reportCount, 5000);
    }
  },
};
export { log };

export const setCookie = (
  name: string,
  value: string,
  options: {
    path?: string;
    secure?: boolean;
    sameSite?: string;
    maxAge?: number;
  } = {},
) => {
  try {
    let cookieString = `${encodeURIComponent(name)}=${encodeURIComponent(
      value,
    )}; path=${options.path || "/"}`;

    if (options.maxAge) {
      cookieString += `; max-age=${options.maxAge}`;
    }

    if (options.secure) {
      cookieString += "; secure";
    }

    if (options.sameSite) {
      cookieString += `; sameSite=${options.sameSite}`;
    }

    document.cookie = cookieString;
    log.info(`Cookie ${name} set successfully: ${value}`);
  } catch (error) {
    log.error(`Error setting cookie ${name}:`, error);
  }
};

export const removeCookie = (
  name: string,
  options: { path?: string; secure?: boolean; sameSite?: string } = {},
) => {
  try {
    setCookie(name, "", {
      path: options.path,
      secure: options.secure,
      sameSite: options.sameSite,
      maxAge: -1,
    });
    log.info(`Cookie ${name} removed successfully.`);
  } catch (error) {
    log.error(`Error removing cookie ${name}:`, error);
    try {
      document.cookie = `${encodeURIComponent(
        name,
      )}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=${options.path || "/"}`;
      log.info(`Fallback cookie removal for ${name} attempted.`);
    } catch (fallbackError) {
      log.error(
        `Even fallback cookie removal failed for ${name}:`,
        fallbackError,
      );
    }
  }
};

export const getCookie = (name: string): string | null => {
  try {
    const cookies = document.cookie.split("; ");
    for (const cookie of cookies) {
      try {
        const [cookieName, cookieValue] = cookie.split("=");
        if (cookieName === encodeURIComponent(name)) {
          return decodeURIComponent(cookieValue);
        }
      } catch (parseError) {
        log.warn(`Error parsing cookie: ${cookie}`, parseError);
      }
    }
    return null;
  } catch (error) {
    log.error(`Error accessing cookies:`, error);
    return null;
  }
};

export const clearAuthData = () => {
  try {
    removeCookie("access_token", {
      secure: !isDebug,
      sameSite: isDebug ? "Lax" : "Strict",
    });
    removeCookie("refresh_token", {
      secure: !isDebug,
      sameSite: isDebug ? "Lax" : "Strict",
    });

    try {
      localStorage.removeItem("userProfile");
      localStorage.removeItem("access_token_expires");
      localStorage.removeItem("refresh_token_expires");
    } catch (localStorageError) {
      log.error("Error clearing localStorage items:", localStorageError);
    }
  } catch (error) {
    log.error("Error in clearAuthData:", error);

    try {
      document.cookie =
        "access_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;";
      document.cookie =
        "refresh_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;";
    } catch (fallbackError) {
      log.error("Fallback cookie clearing failed:", fallbackError);
    }
  }
};

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 10000,
});

let refreshPromise: Promise<string> | null = null;
let refreshAttempts = 0;
const MAX_REFRESH_ATTEMPTS = 3;

export const ACCESS_TOKEN_REFRESH_LEAD_MS = 2 * 60 * 1000;

/** If access JWT is valid longer than this, skip POST /token/refresh/ (another tab refreshed first). */
const ACCESS_SKIP_REFRESH_IF_VALID_BEYOND_MS = 60_000;

let refreshScheduleTimeoutId: ReturnType<typeof setTimeout> | null = null;

class AuthRefreshFatalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthRefreshFatalError";
  }
}

function accessTokenExpiryMsFromJwt(accessToken: string): number | null {
  try {
    const parts = accessToken.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1])) as { exp?: number };
    if (typeof payload.exp !== "number") return null;
    return payload.exp * 1000;
  } catch {
    return null;
  }
}

const getAccessTokenExpiryMs = (): number | null => {
  const accessToken = getCookie("access_token");
  return accessToken ? accessTokenExpiryMsFromJwt(accessToken) : null;
};

const isAccessExpiredOrExpiringSoon = (accessToken: string): boolean => {
  const expMs = accessTokenExpiryMsFromJwt(accessToken);
  if (expMs === null) return true;
  return expMs <= Date.now() + ACCESS_TOKEN_REFRESH_LEAD_MS;
};

function isRefreshRetriableError(err: unknown): boolean {
  if (isAxiosError(err)) {
    const status = err.response?.status;
    if (status === undefined) return true;
    if (status === 429) return true;
    if (status >= 500) return true;
    return false;
  }
  if (err instanceof Error && err.name === "AbortError") return true;
  return false;
}

export const clearRefreshSchedule = (): void => {
  if (refreshScheduleTimeoutId !== null) {
    clearTimeout(refreshScheduleTimeoutId);
    refreshScheduleTimeoutId = null;
  }
};

export const scheduleNextRefreshBeforeExpiry = (): void => {
  clearRefreshSchedule();
  const expiryMs = getAccessTokenExpiryMs();
  if (expiryMs === null) return;
  const delayMs = expiryMs - ACCESS_TOKEN_REFRESH_LEAD_MS - Date.now();
  if (delayMs <= 0) {
    void proactiveRefreshIfNeeded().finally(() => {
      if (getCookie("refresh_token")) scheduleNextRefreshBeforeExpiry();
    });
    return;
  }
  refreshScheduleTimeoutId = setTimeout(() => {
    refreshScheduleTimeoutId = null;
    void proactiveRefreshIfNeeded().finally(() => {
      if (getCookie("refresh_token")) scheduleNextRefreshBeforeExpiry();
    });
  }, delayMs);
};

const handleLogout = () => {
  log.info("Logging out. Clearing authentication data...");
  refreshAttempts = 0;
  clearRefreshSchedule();
  try {
    clearAuthData();
    window.dispatchEvent(new Event("userLoggedOut"));
    setTimeout(() => {
      window.location.href = addPrefix("/login");
    }, 100);
  } catch (error) {
    log.error("Error during logout:", error);
    window.location.href = addPrefix("/login");
  }
};

const JWT_REFRESH_LOCK_NAME = "control.app/jwt-refresh";

function runWithJwtRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator === "undefined" || !navigator.locks?.request) {
    return fn();
  }
  return new Promise((resolve, reject) => {
    void navigator.locks.request(
      JWT_REFRESH_LOCK_NAME,
      { mode: "exclusive" },
      async () => {
        try {
          resolve(await fn());
        } catch (e) {
          reject(e);
        }
      },
    );
  });
}

async function performTokenRefresh(): Promise<string> {
  const accessStillFresh = getCookie("access_token");
  if (accessStillFresh) {
    const expMs = accessTokenExpiryMsFromJwt(accessStillFresh);
    if (
      expMs !== null &&
      expMs > Date.now() + ACCESS_SKIP_REFRESH_IF_VALID_BEYOND_MS
    ) {
      log.info(
        "Skip token refresh: access still valid >60s (e.g. other tab refreshed).",
      );
      refreshAttempts = 0;
      return accessStillFresh;
    }
  }

  if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
    log.error(
      `Maximum refresh attempts (${MAX_REFRESH_ATTEMPTS}) reached. Logging out.`,
    );
    throw new AuthRefreshFatalError("Max refresh attempts reached");
  }

  refreshAttempts++;

  const refreshToken = getCookie("refresh_token");
  if (!refreshToken) {
    log.error("Refresh token not found. Logging out.");
    throw new AuthRefreshFatalError("No refresh token");
  }

  log.info("Attempting to refresh tokens...");

  let response: AxiosResponse;
  try {
    response = await axios.post(
      `${apiUrl}/api/token/refresh/`,
      { refresh: refreshToken },
      { skipAuthInterceptor: true },
    );
  } catch (err: unknown) {
    if (isRefreshRetriableError(err)) {
      log.warn("Token refresh: transient error, will retry on next schedule.");
      throw err;
    }
    if (
      isAxiosError(err) &&
      (err.response?.status === 401 || err.response?.status === 403)
    ) {
      throw new AuthRefreshFatalError("Refresh token rejected");
    }
    throw new AuthRefreshFatalError(
      isAxiosError(err)
        ? `Refresh failed: HTTP ${err.response?.status ?? "?"}`
        : "Refresh failed",
    );
  }

  const newAccessToken = response.data.access;
  const newRefreshToken = response.data.refresh;

  if (!newAccessToken) {
    log.error("No access token in refresh response");
    throw new AuthRefreshFatalError("No access token in response");
  }

  refreshAttempts = 0;

  setCookie("access_token", newAccessToken, {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
    maxAge: jwtCookieMaxAgeSeconds(newAccessToken),
  });

  if (newRefreshToken) {
    setCookie("refresh_token", newRefreshToken, {
      secure: !isDebug,
      sameSite: isDebug ? "Lax" : "Strict",
      maxAge: jwtCookieMaxAgeSeconds(newRefreshToken),
    });
  }

  try {
    if (response.data.access_token_expires) {
      localStorage.setItem(
        "access_token_expires",
        response.data.access_token_expires,
      );
    }
    if (response.data.refresh_token_expires) {
      localStorage.setItem(
        "refresh_token_expires",
        response.data.refresh_token_expires,
      );
    }
  } catch (storageError) {
    log.error(
      "Failed to store token expiration in localStorage:",
      storageError,
    );
  }

  log.info("Tokens refreshed successfully.");

  window.dispatchEvent(
    new CustomEvent("tokensRefreshed", {
      detail: {
        access: newAccessToken,
        refresh: newRefreshToken,
        accessTokenExpires: response.data.access_token_expires,
        refreshTokenExpires: response.data.refresh_token_expires,
      },
    }),
  );

  scheduleNextRefreshBeforeExpiry();

  if (typeof window !== "undefined") {
    try {
      if ("BroadcastChannel" in window) {
        const ch = new BroadcastChannel("auth");
        ch.postMessage({ type: "tokens-refreshed", timestamp: Date.now() });
        ch.close();
      }
      localStorage.setItem("app:authSync", String(Date.now()));
    } catch {
      // ignore
    }
  }

  return newAccessToken;
}

const refreshTokens = async (): Promise<string> => {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = runWithJwtRefreshLock(() => performTokenRefresh())
    .catch((err: unknown) => {
      if (isRefreshRetriableError(err)) {
        refreshAttempts = Math.max(0, refreshAttempts - 1);
        if (getCookie("refresh_token")) {
          scheduleNextRefreshBeforeExpiry();
        }
        return Promise.reject(err);
      }
      log.error("Failed to refresh tokens.", err);
      handleLogout();
      return Promise.reject(err);
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
};

export const proactiveRefreshIfNeeded = async (): Promise<void> => {
  const refreshToken = getCookie("refresh_token");
  if (!refreshToken) return;
  const accessToken = getCookie("access_token");
  if (accessToken && !isAccessExpiredOrExpiringSoon(accessToken)) return;
  try {
    await refreshTokens();
  } catch {
    if (isDebug) {
      log.info("Proactive refresh failed (handled in refreshTokens)");
    }
  }
};

axiosInstance.interceptors.request.use(
  async (config) => {
    if (config.skipAuthInterceptor) {
      return config;
    }

    if (config.data instanceof FormData) {
      delete config.headers["Content-Type"];
    } else if (
      config.data &&
      typeof config.data === "object" &&
      !config.headers["Content-Type"]
    ) {
      config.headers["Content-Type"] = "application/json;charset=utf-8";
    }

    try {
      let accessToken = getCookie("access_token");
      const refreshToken = getCookie("refresh_token");

      const needRefresh =
        refreshToken &&
        (!accessToken || isAccessExpiredOrExpiringSoon(accessToken));

      if (needRefresh) {
        try {
          accessToken = await refreshTokens();
        } catch (err) {
          return Promise.reject(err);
        }
      }

      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
      }

      return config;
    } catch (error) {
      log.error("Error in request interceptor:", error);
      return config;
    }
  },
  (error) => {
    log.error("Request interceptor error:", error);
    return Promise.reject(error);
  },
);

axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error) => {
    if (error.config?.skipAuthInterceptor) {
      return Promise.reject(error);
    }

    try {
      if (
        (error.response?.status === 401 || error.response?.status === 403) &&
        !error.config._retry &&
        getCookie("refresh_token")
      ) {
        error.config._retry = true;

        try {
          const accessToken = await refreshTokens();
          error.config.headers.Authorization = `Bearer ${accessToken}`;
          return axiosInstance(error.config);
        } catch (refreshError) {
          return Promise.reject(refreshError);
        }
      }
    } catch (interceptorError) {
      log.error("Error in response interceptor:", interceptorError);
    }

    return Promise.reject(error);
  },
);

export default axiosInstance;
