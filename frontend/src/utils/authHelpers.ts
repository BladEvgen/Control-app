import { log } from "../api";
import { getCookie, clearAuthData } from "../api";

export const isTokenValid = (token: string | null): boolean => {
  if (!token) return false;

  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;

    const payload = JSON.parse(atob(parts[1]));

    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return false;
    }

    return true;
  } catch (error) {
    log.error("Error validating token:", error);
    return false;
  }
};

export const isAuthenticated = (): boolean => {
  try {
    const accessToken = getCookie("access_token");
    const refreshToken = getCookie("refresh_token");

    if (!refreshToken) {
      if (accessToken) {
        log.warn("Access token present but no refresh token");
      }
      clearAuthData();
      return false;
    }

    if (accessToken && isTokenValid(accessToken)) {
      return true;
    }

    if (accessToken && !isTokenValid(accessToken)) {
      log.info(
        "Access token invalid/expired but refresh token exists, continuing auth flow",
      );
      return true;
    }

    return true;
  } catch (error) {
    log.error("Error in isAuthenticated check:", error);
    clearAuthData();
    return false;
  }
};

export const getUsername = (): string => {
  try {
    return getCookie("username") || "";
  } catch (error) {
    log.error("Error getting username:", error);
    return "";
  }
};

export const logoutUser = (
  navigate: (path: string) => void,
  extraCallback?: () => void,
): void => {
  try {
    clearAuthData();

    if (extraCallback) {
      extraCallback();
    }

    window.dispatchEvent(new Event("userLoggedOut"));

    navigate("/login");
  } catch (error) {
    log.error("Error during logout:", error);

    try {
      window.location.href = "/app/login";
    } catch (redirectError) {
      log.error("Even redirect failed:", redirectError);
    }
  }
};
