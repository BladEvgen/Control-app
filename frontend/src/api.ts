import Cookies from "js-cookie";
import { addPrefix } from "./RouterUtils";
import axios, { AxiosResponse } from "axios";
import { apiUrl, isDebug } from "../apiConfig";

const setCookie = (name: string, value: string, options = {}) => {
  Cookies.set(name, value, {
    path: "/",
    secure: !isDebug,
    sameSite: "Strict",
    maxAge: 3600,
    ...options,
  });
};

const removeCookie = (name: string, options = {}) => {
  Cookies.remove(name, {
    path: "/",
    secure: !isDebug,
    sameSite: "Strict",
    ...options,
  });
};

const getCookie = (name: string) => {
  const cookieValue = Cookies.get(name);
  return cookieValue !== undefined ? cookieValue : null;
};

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 5000,
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
        const refreshResponse = await axios.post(
          `${apiUrl}/api/token/refresh/`,
          {
            refresh: getCookie("refresh_token"),
          }
        );

        const newAccessToken = refreshResponse.data.access;
        const newRefreshToken = refreshResponse.data.refresh;

        setCookie("access_token", newAccessToken);
        setCookie("refresh_token", newRefreshToken);

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return axiosInstance(originalRequest);
      } catch (refreshError: any) {
        if (
          refreshError.response?.status === 401 ||
          refreshError.response?.status === 403
        ) {
          handleLogout();
        }
        return Promise.reject(refreshError);
      }
    }

    if (error.response?.status === 401) {
      handleLogout();
    }

    return Promise.reject(error);
  }
);

const handleLogout = () => {
  removeCookie("access_token");
  removeCookie("refresh_token");
  removeCookie("username");

  window.location.replace(addPrefix("/login"));
};

export default axiosInstance;
