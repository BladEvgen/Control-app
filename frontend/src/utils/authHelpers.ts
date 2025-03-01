import { getCookie, clearAuthData } from "../api";

/**
 * Проверяет, авторизован ли пользователь.
 * Если отсутствуют оба токена — очищает данные.
 */
export const isAuthenticated = (): boolean => {
  const accessToken = getCookie("access_token");
  const refreshToken = getCookie("refresh_token");
  if (!accessToken && !refreshToken) {
    clearAuthData();
  }
  return Boolean(accessToken && refreshToken);
};

export const getUsername = (): string => {
  return getCookie("username") || "";
};

/**
 * Выполняет выход пользователя:
 *  - Очищает куки и профиль (через clearAuthData),
 *  - Вызывает дополнительную callback-функцию (если требуется, например, для обновления UI),
 *  - Перенаправляет на страницу логина.
 *
 * @param navigate Функция для навигации
 * @param extraCallback Опциональный callback для дополнительных действий.
 */
export const logoutUser = (
  navigate: (path: string) => void,
  extraCallback?: () => void
): void => {
  clearAuthData();
  if (extraCallback) {
    extraCallback();
  }
  window.dispatchEvent(new Event("userLoggedOut"));
  navigate("/login");
};
