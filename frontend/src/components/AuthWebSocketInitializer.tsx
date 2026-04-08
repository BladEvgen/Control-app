import { useEffect, useMemo, useRef, useCallback } from "react";
import { useAppSelector, useAppDispatch } from "../store/hooks";
import type { RootState } from "../store";
import { setUser, logout } from "../store/slices/authSlice";
import { getCookie, log, proactiveRefreshIfNeeded } from "../api";
import { apiUrl } from "../../apiConfig";
import useWebSocket from "../hooks/useWebSocket";
import { isTokenValid } from "../utils/authHelpers";

const wsLog = (msg: string, data?: unknown) => {
  log.info(`[WS-Auth] ${msg}`, data ?? "");
};

const AuthWebSocketInitializer: React.FC = () => {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state: RootState) => state.auth.token);
  const wsReconnectRef = useRef<(() => void) | null>(null);
  const releaseTokenRefreshLockRef = useRef<(() => void) | null>(null);

  const hasValidToken = Boolean(token && isTokenValid(token));
  const refreshTokenPresent = Boolean(getCookie("refresh_token"));
  const needsRefreshBeforeConnect =
    token && !isTokenValid(token) && refreshTokenPresent;

  const handleTokenRefresh = useCallback(async () => {
    try {
      log.info("WebSocket требует обновления токена. Пытаемся обновить...");
      const rt = getCookie("refresh_token");
      if (!rt) {
        log.error("Refresh токен не найден. Выполняем логаут.");
        dispatch(logout());
        window.dispatchEvent(new Event("userLoggedOut"));
        return;
      }

      await proactiveRefreshIfNeeded();
      log.info(
        "Токен успешно обновлен. WebSocket переподключится с новым токеном.",
      );

      if (wsReconnectRef.current) {
        setTimeout(() => {
          wsReconnectRef.current?.();
        }, 300);
      }
    } catch (error) {
      log.error("Ошибка обновления токена:", error);
      releaseTokenRefreshLockRef.current?.();
      dispatch(logout());
      window.dispatchEvent(new Event("userLoggedOut"));
    }
  }, [dispatch]);

  const handleRefreshExpired = useCallback(() => {
    log.error("Refresh токен истек. Выполняем логаут.");
    dispatch(logout());
    window.dispatchEvent(new Event("userLoggedOut"));
  }, [dispatch]);

  useEffect(() => {
    if (needsRefreshBeforeConnect) {
      void proactiveRefreshIfNeeded();
    }
  }, [needsRefreshBeforeConnect]);

  const wsUrl = useMemo(() => {
    if (!hasValidToken || !token) return null;
    const urlObj = new URL(apiUrl);
    const protocol = urlObj.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${urlObj.host}/ws/user-detail/?token=${token}`;
  }, [hasValidToken, token]);

  const { reconnect, releaseTokenRefreshLock } = useWebSocket({
    url: wsUrl || "",
    onMessage: (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        wsLog("сообщение", {
          type: data?.type,
          hasUserProfile: !!data?.user_profile,
        });

        if (data.type === "pong" && data.user_profile) {
          wsLog("профиль из heartbeat", data.user_profile?.username);
          dispatch(setUser(data.user_profile));
          return;
        }
        if (data.type === "user_profile") {
          const userData = data.user ?? data;
          if (userData?.id || userData?.username) {
            wsLog("профиль из user_profile", userData?.username);
            dispatch(setUser(userData));
          }
          return;
        }
        if (data.error === "token_expired" || data.action === "refresh_token") {
          wsLog("токен истек, refresh");
          handleTokenRefresh();
          return;
        }
        if (data.error) {
          wsLog("ошибка", data.error);
          log.error("Error getting profile:", data.error);
        }
      } catch (error) {
        wsLog("ошибка парсинга", error);
        log.error("Error parsing WS message:", error);
      }
    },
    onOpen: () => {
      wsLog("onOpen - профиль придет с первым pong (heartbeat)");
    },
    onTokenExpired: handleTokenRefresh,
    onRefreshExpired: handleRefreshExpired,
  });

  useEffect(() => {
    wsReconnectRef.current = reconnect || null;
    releaseTokenRefreshLockRef.current = releaseTokenRefreshLock;
  }, [reconnect, releaseTokenRefreshLock]);

  return null;
};

export default AuthWebSocketInitializer;
