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
};

export const removeCookie = (
  name: string,
  options: { path?: string; secure?: boolean; sameSite?: string } = {}
) => {
  setCookie(name, "", {
    path: options.path,
    secure: options.secure,
    sameSite: options.sameSite,
    maxAge: -1,
  });
  log.info(`Cookie ${name} removed successfully.`);
};

export const getCookie = (name: string): string | null => {
  const cookies = document.cookie.split("; ");
  for (let cookie of cookies) {
    const [cookieName, cookieValue] = cookie.split("=");
    if (cookieName === encodeURIComponent(name)) {
      return decodeURIComponent(cookieValue);
    }
  }
  log.warn(`Cookie ${name} not found.`);
  return null;
};

export const clearAuthData = () => {
  removeCookie("access_token", {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  });
  removeCookie("refresh_token", {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  });
  localStorage.removeItem("userProfile");
};

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 10000,
  headers: {
    "Content-Type": "application/json;charset=utf-8",
  },
});

let refreshPromise: Promise<string> | null = null;

const refreshTokens = async (): Promise<string> => {
  if (refreshPromise) {
    return refreshPromise;
  }

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

      localStorage.setItem(
        "access_token_expires",
        response.data.access_token_expires
      );
      localStorage.setItem(
        "refresh_token_expires",
        response.data.refresh_token_expires
      );

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
  },
  (error) => Promise.reject(error)
);

axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error) => {
    const originalRequest = error.config;

    if (originalRequest.skipAuthInterceptor) {
      return Promise.reject(error);
    }

    if (
      (error.response?.status === 401 || error.response?.status === 403) &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;
      try {
        const accessToken = await refreshTokens();
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return axiosInstance(originalRequest);
      } catch (err) {
        return Promise.reject(err);
      }
    }
    return Promise.reject(error);
  }
);

const handleLogout = () => {
  log.info("Logging out. Clearing authentication data...");
  clearAuthData();
  window.dispatchEvent(new Event("userLoggedOut"));
  window.location.href = addPrefix("/login");
};

export default axiosInstance;
