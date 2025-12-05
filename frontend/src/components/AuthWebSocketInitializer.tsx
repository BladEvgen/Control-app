import { useEffect, useMemo, useRef, useCallback } from "react";
import { useAppSelector, useAppDispatch } from "../store/hooks";
import { setUser, setTokens, logout } from "../store/slices/authSlice";
import { getCookie } from "../api";
import { apiUrl } from "../../apiConfig";
import useWebSocket from "../hooks/useWebSocket";
import { log } from "../api";
import axiosInstance from "../api";

const AuthWebSocketInitializer: React.FC = () => {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const wsReconnectRef = useRef<(() => void) | null>(null);

  const handleTokenRefresh = useCallback(async () => {
    try {
      log.info("WebSocket требует обновления токена. Пытаемся обновить...");
      const refreshToken = getCookie("refresh_token");
      if (!refreshToken) {
        log.error("Refresh токен не найден. Выполняем логаут.");
        dispatch(logout());
        window.dispatchEvent(new Event("userLoggedOut"));
        return;
      }

      const response = await axiosInstance.post(
        "/token/refresh/",
        { refresh: refreshToken },
        { skipAuthInterceptor: true }
      );

      const newAccessToken = response.data.access;
      const newRefreshToken = response.data.refresh;

      if (!newAccessToken) {
        log.error("Не удалось получить новый access токен. Выполняем логаут.");
        dispatch(logout());
        window.dispatchEvent(new Event("userLoggedOut"));
        return;
      }

      dispatch(setTokens({
        access: newAccessToken,
        refresh: newRefreshToken,
        accessTokenExpires: response.data.access_token_expires,
        refreshTokenExpires: response.data.refresh_token_expires,
      }));

      window.dispatchEvent(
        new CustomEvent("tokensRefreshed", {
          detail: {
            access: newAccessToken,
            refresh: newRefreshToken,
            accessTokenExpires: response.data.access_token_expires,
            refreshTokenExpires: response.data.refresh_token_expires,
          },
        })
      );

      log.info("Токен успешно обновлен. Переподключаем WebSocket...");
      
      if (wsReconnectRef.current) {
        setTimeout(() => {
          wsReconnectRef.current?.();
        }, 500);
      }
    } catch (error) {
      log.error("Ошибка обновления токена:", error);
      dispatch(logout());
      window.dispatchEvent(new Event("userLoggedOut"));
    }
  }, [dispatch]);

  const handleRefreshExpired = useCallback(() => {
    log.error("Refresh токен истек. Выполняем логаут.");
    dispatch(logout());
    window.dispatchEvent(new Event("userLoggedOut"));
  }, [dispatch]);

  const wsUrl = useMemo(() => {
    if (!token) return null;
    const urlObj = new URL(apiUrl);
    const protocol = urlObj.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${urlObj.host}/ws/user-detail/?token=${token}`;
  }, [token]);

  const { sendMessage, reconnect } = useWebSocket({
    url: wsUrl || "",
    onMessage: (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        log.info("AuthWebSocketInitializer received WS message:", data);
        
        if (data.type === "user_profile") {
          if (data.user) {
            dispatch(setUser(data.user));
          } else if (data.id) {
            dispatch(setUser(data));
          }
        } else if (data.error === "token_expired" || data.action === "refresh_token") {
          log.warn("Получено сообщение об истечении токена от WebSocket");
          handleTokenRefresh();
        } else if (data.error) {
          log.error("Error getting profile:", data.error);
        } else if (data.user) {
          dispatch(setUser(data.user));
        } else if (data.id) {
          dispatch(setUser(data));
        }
      } catch (error) {
        log.error("Error parsing WS message:", error);
      }
    },
    onOpen: () => {
      if (wsUrl) {
        sendMessage(JSON.stringify({ action: "get_profile" }));
      }
    },
    onTokenExpired: handleTokenRefresh,
    onRefreshExpired: handleRefreshExpired,
  });

  useEffect(() => {
    wsReconnectRef.current = reconnect || null;
  }, [reconnect]);

  return null;
};

export default AuthWebSocketInitializer;

