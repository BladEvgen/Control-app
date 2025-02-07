import { isDebug } from "../../apiConfig";
import { getCookie, removeCookie } from "../api";

export const isAuthenticated = (): boolean => {
  return Boolean(getCookie("access_token"));
};

export const getUsername = (): string => {
  return getCookie("username") || "";
};

export const logoutUser = (
  navigate: (path: string) => void,
  extraCallback?: () => void
): void => {
  const cookieOptions = {
    secure: !isDebug,
    sameSite: isDebug ? "Lax" : "Strict",
  };

  ["access_token", "refresh_token", "username"].forEach((cookieName) => {
    removeCookie(cookieName, cookieOptions);
  });

  if (extraCallback) {
    extraCallback();
  }

  navigate("/login");
};
