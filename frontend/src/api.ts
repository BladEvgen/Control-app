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

    if (
      (error.response?.status === 401 || error.response?.status === 403) &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;
      try {
        const refreshToken = getCookie("refresh_token");
        if (!refreshToken) {
          log.error("Отсутствует refresh_token.");
          handleLogout();
          return Promise.reject(error);
        }

        const refreshResponse = await axios.post(
          `${apiUrl}/api/token/refresh/`,
          {
            refresh: refreshToken,
          }
        );

        const newAccessToken = refreshResponse.data.access;
        const newRefreshToken = refreshResponse.data.refresh;

        setCookie("access_token", newAccessToken, {
          secure: !isDebug,
          sameSite: isDebug ? "Lax" : "Strict",
          maxAge: 3600,
        });
        setCookie("refresh_token", newRefreshToken, {
          secure: !isDebug,
          sameSite: isDebug ? "Lax" : "Strict",
          maxAge: 3600,
        });

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return axiosInstance(originalRequest);
      } catch (refreshError: any) {
        if (
          refreshError.response?.status === 401 ||
          refreshError.response?.status === 403
        ) {
          log.error("Не удалось обновить токен. Выполняем выход.");
          handleLogout();
        }
        return Promise.reject(refreshError);
      }
    }

    if (error.response?.status === 401) {
      log.error("401 ошибка. Выполняем выход.");
      handleLogout();
    }

    return Promise.reject(error);
  }
);

const handleLogout = () => {
  log.info("Выполняем выход. Удаление токенов...");
  removeCookie("access_token", {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  });
  removeCookie("refresh_token", {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  });
  removeCookie("username", {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  });

  window.location.href = addPrefix("/login");
};

export default axiosInstance;
