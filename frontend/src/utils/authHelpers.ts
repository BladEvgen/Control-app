import { getCookie, removeCookie } from "../api";

export const isAuthenticated = (): boolean => {
  const accessToken = getCookie("access_token");
  const refreshToken = getCookie("refresh_token");
  return Boolean(accessToken && refreshToken); 
};

export const getUsername = (): string => {
  return getCookie("username") || "";
};

/**
 * Выполняет выход пользователя:
 *  - удаляет cookie,
 *  - удаляет профиль из localStorage,
 *  - выполняет дополнительную callback-функцию (для обновления UI),
 *  - перенаправляет на страницу логина.
 *
 * @param navigate Функция для навигации
 * @param extraCallback Опциональная callback-функция для дополнительных действий (например, сброс состояния)
 */
export const logoutUser = (
  navigate: (path: string) => void,
  extraCallback?: () => void
): void => {
  removeCookie("access_token");
  removeCookie("refresh_token");
  localStorage.removeItem("userProfile");

  if (extraCallback) {
    extraCallback();
  }
  navigate("/login");
};
