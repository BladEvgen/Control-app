import Cookies from "js-cookie";
import { apiUrl } from "../apiConfig";
import axios, { AxiosResponse } from "axios";

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 5000,
  headers: {
    "Content-Type": "application/json;charset=utf-8",
  },
});

axiosInstance.interceptors.request.use(
  (config) => {
    const accessToken = Cookies.get("access_token");
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    if ((error.response.status === 401 || error.response.status === 403) && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshResponse = await axios.post(`${apiUrl}/api/token/refresh/`, { refresh: Cookies.get("refresh_token") });

        const newAccessToken = refreshResponse.data.access;
        const newRefreshToken = refreshResponse.data.refresh;

        Cookies.set("access_token", newAccessToken, { path: "/" });
        Cookies.set("refresh_token", newRefreshToken, { path: "/" });

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return axiosInstance(originalRequest);
      } catch (refreshError: any) {
        if (refreshError.response.status === 401 || refreshError.response.status === 403) {
          Cookies.remove("access_token", { path: "/" });
          Cookies.remove("refresh_token", { path: "/" });


          window.location.reload();
        }
        
        return Promise.reject(refreshError);
      }
    } else if (error.response.status === 401) {
      Cookies.remove("access_token", { path: "/" });
      Cookies.remove("refresh_token", { path: "/" });


      window.location.reload();
    }

    return Promise.reject(error);
  }
);

export default axiosInstance;
