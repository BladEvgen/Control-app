import { addPrefix } from "./RouterUtils";
import axios, { AxiosResponse } from "axios";
import { apiUrl, isDebug } from "../apiConfig";
import { BaseAction } from "./schemas/BaseAction";

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
  log.info(`Кука ${name} успешно установлена: ${value}`);
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
  log.info(`Кука ${name} успешно удалена.`);
};

export const getCookie = (name: string): string | null => {
  const cookies = document.cookie.split("; ");
  for (let cookie of cookies) {
    const [cookieName, cookieValue] = cookie.split("=");
    if (cookieName === encodeURIComponent(name)) {
      return decodeURIComponent(cookieValue);
    }
  }
  log.warn(`Кука ${name} не найдена.`);
  return null;
};

const tokenManager = {
  isRefreshing: false,
  refreshSubscribers: [] as ((token: string) => void)[],

  subscribeTokenRefresh(callback: (token: string) => void) {
    this.refreshSubscribers.push(callback);
  },

  onTokenRefreshed(token: string) {
    this.refreshSubscribers.forEach((callback) => callback(token));
    this.refreshSubscribers = [];
  },

  async refreshTokenPair() {
    const refreshToken = getCookie("refresh_token");
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

    const response = await axios.post(
      `${apiUrl}/api/token/refresh/`,
      { refresh: refreshToken },
      { skipAuthInterceptor: true }
    );

    const { access, refresh } = response.data;
    this.setTokens(access, refresh);
    return access;
  },

  setTokens(accessToken: string, refreshToken: string) {
    setCookie("access_token", accessToken, {
      secure: !isDebug,
      sameSite: isDebug ? "Lax" : "Strict",
      maxAge: 600,
    });
    setCookie("refresh_token", refreshToken, {
      secure: !isDebug,
      sameSite: isDebug ? "Lax" : "Strict",
      maxAge: 3600,
    });
  },
};

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 10000,
  headers: {
    "Content-Type": "application/json;charset=utf-8",
  },
});

axiosInstance.interceptors.request.use(
  (config) => {
    const accessToken = getCookie("access_token");
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

    if (originalRequest?.skipAuthInterceptor) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (!tokenManager.isRefreshing) {
        tokenManager.isRefreshing = true;
        try {
          const newAccessToken = await tokenManager.refreshTokenPair();
          tokenManager.onTokenRefreshed(newAccessToken);
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return axiosInstance(originalRequest);
        } catch (refreshError) {
          handleLogout();
          return Promise.reject(
            BaseAction.createAction(
              BaseAction.SET_ERROR,
              "Failed to refresh token"
            )
          );
        } finally {
          tokenManager.isRefreshing = false;
        }
      } else {
        return new Promise((resolve) => {
          tokenManager.subscribeTokenRefresh((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(axiosInstance(originalRequest));
          });
        });
      }
    }

    return Promise.reject(error);
  }
);

export const handleLogout = () => {
  log.info("Performing logout. Removing tokens...");
  const cookieOptions = {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  };

  ["access_token", "refresh_token", "username"].forEach((cookieName) => {
    removeCookie(cookieName, cookieOptions);
  });

  window.location.href = addPrefix("/login");
};

export default axiosInstance;
export { tokenManager };
