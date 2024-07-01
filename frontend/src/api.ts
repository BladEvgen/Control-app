import axios from "axios";
import Cookies from "js-cookie";
import { apiUrl } from "../apiConfig";
import { useNavigate } from "./RouterUtils";

const axiosInstance = axios.create({
  baseURL: `${apiUrl}/api`,
  timeout: 5000,
  headers: {
    "Content-Type": "application/json;charset=utf-8",
  }
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
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    const navigate = useNavigate();
    
    if ((error.response.status === 401 || error.response.status === 403) && !originalRequest._retry) {
      originalRequest._retry = true;
      
      try {
        const refreshToken = Cookies.get("refresh_token");
        if (!refreshToken) {
          console.error("No refresh token available");
          Cookies.remove("access_token", { path: "/" });
          Cookies.remove("refresh_token", { path: "/" });
          navigate("/login");
          return Promise.reject(error);
        }

        console.log("Attempting to refresh token...");

        const response = await axios.post(`${apiUrl}/api/token/refresh/`, {
          refresh: refreshToken,
        });

        const newAccessToken = response.data.access;
        const newRefreshToken = response.data.refresh;

        Cookies.set("access_token", newAccessToken, { path: "/" });
        Cookies.set("refresh_token", newRefreshToken, { path: "/" });

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return axiosInstance(originalRequest);
      } catch (refreshError) {
        console.error("Failed to refresh token", refreshError);
        Cookies.remove("access_token", { path: "/" });
        Cookies.remove("refresh_token", { path: "/" });
        navigate("/login");
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

export default axiosInstance;
