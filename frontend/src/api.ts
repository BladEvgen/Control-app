import { addPrefix } from "./RouterUtils";
import axios, { AxiosResponse } from "axios";
import { apiUrl, isDebug } from "../apiConfig";

const log = {
  info: (...args: any[]) => {
    if (isDebug) {
      console.log(`%cINFO:`, "color: green; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  warn: (...args: any[]) => {
    if (isDebug) {
      console.log(`%cWARN:`, "color: orange; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  error: (...args: any[]) => {
    if (isDebug) {
      console.error(`%cERROR:`, "color: red; font-weight: bold;", ...args);
    } else {
      log.prodWarning();
    }
  },
  prodWarning: () => {
    console.log(
      "%cWARNING:",
      "color: yellow; font-weight: bold; font-size: 16px;",
      "This function is intended for developers. If you're an ordinary user, it's better to close this."
    );
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
  } = {}
) => {
  try {
    let cookieString = `${encodeURIComponent(name)}=${encodeURIComponent(
      value
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
  options: { path?: string; secure?: boolean; sameSite?: string } = {}
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
        name
      )}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=${options.path || "/"}`;
      log.info(`Fallback cookie removal for ${name} attempted.`);
    } catch (fallbackError) {
      log.error(
        `Even fallback cookie removal failed for ${name}:`,
        fallbackError
      );
    }
  }
};

export const getCookie = (name: string): string | null => {
  try {
    const cookies = document.cookie.split("; ");
    for (let cookie of cookies) {
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
  headers: {
    "Content-Type": "application/json;charset=utf-8",
  },
});

let refreshPromise: Promise<string> | null = null;
let refreshAttempts = 0;
const MAX_REFRESH_ATTEMPTS = 3;

const resetRefreshAttempts = () => {
  setTimeout(() => {
    refreshAttempts = 0;
  }, 60000);
};

const refreshTokens = async (): Promise<string> => {
  if (refreshPromise) {
    return refreshPromise;
  }

  if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
    log.error(
      `Maximum refresh attempts (${MAX_REFRESH_ATTEMPTS}) reached. Logging out.`
    );
    handleLogout();
    resetRefreshAttempts();
    return Promise.reject(new Error("Max refresh attempts reached"));
  }

  refreshAttempts++;

  const refreshToken = getCookie("refresh_token");
  if (!refreshToken) {
    log.error("Refresh token not found. Logging out.");
    handleLogout();
    return Promise.reject(new Error("No refresh token"));
  }

  log.info("Attempting to refresh tokens...");
  refreshPromise = axios
    .post(
      `${apiUrl}/api/token/refresh/`,
      { refresh: refreshToken },
      { skipAuthInterceptor: true }
    )
    .then((response) => {
      const newAccessToken = response.data.access;
      const newRefreshToken = response.data.refresh;

      refreshAttempts = 0;

      setCookie("access_token", newAccessToken, {
        secure: !isDebug,
        sameSite: isDebug ? "Lax" : "Strict",
        maxAge: 1800,
      });
      setCookie("refresh_token", newRefreshToken, {
        secure: !isDebug,
        sameSite: isDebug ? "Lax" : "Strict",
        maxAge: 7200,
      });

      try {
        localStorage.setItem(
          "access_token_expires",
          response.data.access_token_expires
        );
        localStorage.setItem(
          "refresh_token_expires",
          response.data.refresh_token_expires
        );
      } catch (storageError) {
        log.error(
          "Failed to store token expiration in localStorage:",
          storageError
        );
      }

      log.info("Tokens refreshed successfully.");
      refreshPromise = null;
      return newAccessToken;
    })
    .catch((err) => {
      refreshPromise = null;
      log.error("Failed to refresh tokens.", err);
      handleLogout();
      return Promise.reject(err);
    });

  return refreshPromise;
};

axiosInstance.interceptors.request.use(
  async (config) => {
    if (config.skipAuthInterceptor) {
      return config;
    }

    try {
      let accessToken = getCookie("access_token");
      const refreshToken = getCookie("refresh_token");

      if (!accessToken && refreshToken) {
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
  }
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
  }
);

const handleLogout = () => {
  log.info("Logging out. Clearing authentication data...");
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

export default axiosInstance;
