import { log } from "../api";
import { getCookie, clearAuthData } from "../api";

const isTokenValid = (token: string | null): boolean => {
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

    if (accessToken && !isTokenValid(accessToken)) {
      if (!refreshToken) {
        log.warn("Invalid access token and no refresh token found");
        clearAuthData();
        return false;
      }

      log.info(
        "Access token invalid but refresh token exists, continuing auth flow"
      );
      return true;
    }

    const hasTokens = Boolean(accessToken && refreshToken);

    if (!hasTokens) {
      clearAuthData();
    }

    return hasTokens;
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
  extraCallback?: () => void
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
