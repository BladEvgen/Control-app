import { log } from "../api";
import { useEffect, useRef, useCallback, useState } from "react";

const wsLog = (msg: string, data?: unknown) => {
  try {
    console.info(`[WS] ${msg}`, data ?? "");
  } catch {
    console.info(`[WS] ${msg}`);
  }
};

const WS_CLOSE_TOKEN_EXPIRED = 4001;
const WS_CLOSE_TOKEN_INVALID = 4002;
const WS_CLOSE_REFRESH_EXPIRED = 4003;
const WS_CLOSE_AUTH_FAILED = 4004;

interface UseWebSocketOptions {
  url: string | null;
  onMessage: (event: MessageEvent) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
  shouldReconnect?: boolean;
  reconnectInterval?: number;
  pingInterval?: number;
  pongTimeout?: number;
  onTokenExpired?: () => void;
  onRefreshExpired?: () => void;
}

const useWebSocket = ({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  shouldReconnect = true,
  reconnectInterval = 5000,
  pingInterval = 30000,
  pongTimeout = 10000,
  onTokenExpired,
  onRefreshExpired,
}: UseWebSocketOptions) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef<boolean>(false);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRefLocal = useRef<number | null>(null);
  const attemptRef = useRef<number>(0);
  const urlRef = useRef<string | null>(url);
  const isRefreshingTokenRef = useRef<boolean>(false);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  const onOpenRef = useRef<() => void>();
  const onCloseRef = useRef<(event: CloseEvent) => void>();
  const onErrorRef = useRef<(event: Event) => void>();
  const onMessageRef = useRef<(event: MessageEvent) => void>();
  const onTokenExpiredRef = useRef<(() => void) | undefined>();
  const onRefreshExpiredRef = useRef<(() => void) | undefined>();

  useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onTokenExpiredRef.current = onTokenExpired;
  }, [onTokenExpired]);

  useEffect(() => {
    onRefreshExpiredRef.current = onRefreshExpired;
  }, [onRefreshExpired]);

  const handlePong = useCallback(() => {
    wsLog("pong получен");
    if (pongTimeoutRefLocal.current) {
      clearTimeout(pongTimeoutRefLocal.current);
      pongTimeoutRefLocal.current = null;
    }
    attemptRef.current = 0;
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsLog("ping отправлен");
      wsRef.current.send(JSON.stringify({ type: "ping" }));

      pongTimeoutRefLocal.current = window.setTimeout(() => {
        log.warn("Не получен pong от сервера, закрытие соединения");
        wsRef.current?.close();
      }, pongTimeout);
    }
  }, [pongTimeout]);

  const connect = useCallback(() => {
    if (!urlRef.current) {
      wsLog("URL не задан, соединение не устанавливается");
      return;
    }
    wsLog("подключение", urlRef.current);
    wsRef.current = new WebSocket(urlRef.current);

    wsRef.current.onopen = () => {
      wsLog("соединение установлено");
      setIsConnected(true);
      onOpenRef.current?.();

      pingIntervalRef.current = window.setInterval(sendPing, pingInterval);

      sendPing();

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      attemptRef.current = 0;
    };

    wsRef.current.onmessage = (event: MessageEvent) => {
      const dataStr = typeof event.data === "string" ? event.data : "";
      setTimeout(() => {
        try {
          const data = JSON.parse(dataStr);
          wsLog("сообщение", {
            type: data?.type,
            hasProfile: !!data?.user_profile,
          });

          if (data.type === "pong") {
            handlePong();
            if (data.user_profile) {
              onMessageRef.current?.({
                ...event,
                data: dataStr,
              } as MessageEvent);
            }
            return;
          }
          if (data.type === "heartbeat") return;

          if (
            data.error === "token_expired" ||
            data.action === "refresh_token"
          ) {
            log.warn("Получено сообщение об истечении токена от WebSocket");
            if (!isRefreshingTokenRef.current && onTokenExpiredRef.current) {
              isRefreshingTokenRef.current = true;
              onTokenExpiredRef.current();
            }
            return;
          }

          onMessageRef.current?.({ ...event, data: dataStr } as MessageEvent);
        } catch (error) {
          wsLog("ошибка обработки", error);
          log.error("Ошибка при обработке сообщения WebSocket:", error);
        }
      }, 0);
    };

    wsRef.current.onclose = (event: CloseEvent) => {
      setIsConnected(false);
      wsLog("соединение закрыто", { code: event.code, reason: event.reason });

      if (
        event.code === WS_CLOSE_TOKEN_EXPIRED ||
        event.code === WS_CLOSE_TOKEN_INVALID
      ) {
        log.warn(
          "WebSocket закрыт из-за истечения/невалидности токена. Обновляем токен...",
        );
        if (!isRefreshingTokenRef.current && onTokenExpiredRef.current) {
          isRefreshingTokenRef.current = true;
          onTokenExpiredRef.current();
        }
        onCloseRef.current?.(event);
        return;
      }

      if (event.code === WS_CLOSE_REFRESH_EXPIRED) {
        log.error("Refresh токен истек. Выполняем логаут...");
        if (onRefreshExpiredRef.current) {
          onRefreshExpiredRef.current();
        }
        onCloseRef.current?.(event);
        return;
      }

      if (event.code === WS_CLOSE_AUTH_FAILED) {
        log.error("Ошибка аутентификации WebSocket");
        if (onRefreshExpiredRef.current) {
          onRefreshExpiredRef.current();
        }
        onCloseRef.current?.(event);
        return;
      }

      onCloseRef.current?.(event);

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      if (pongTimeoutRefLocal.current) {
        clearTimeout(pongTimeoutRefLocal.current);
        pongTimeoutRefLocal.current = null;
      }

      if (
        shouldReconnect &&
        isMountedRef.current &&
        !isRefreshingTokenRef.current
      ) {
        const nextReconnectInterval = Math.min(
          reconnectInterval * 2 ** attemptRef.current,
          60000,
        );
        wsLog(`переподключение через ${nextReconnectInterval} мс`);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          attemptRef.current += 1;
          connect();
        }, nextReconnectInterval);
      }
    };

    wsRef.current.onerror = (error) => {
      wsLog("ошибка WebSocket", error);
      onErrorRef.current?.(error);
      wsRef.current?.close();
    };
  }, [handlePong, pingInterval, reconnectInterval, sendPing, shouldReconnect]);

  useEffect(() => {
    isMountedRef.current = true;
    urlRef.current = url;
    isRefreshingTokenRef.current = false;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (pongTimeoutRefLocal.current) {
        clearTimeout(pongTimeoutRefLocal.current);
      }
      wsRef.current?.close();
    };
  }, [connect, url]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      wsLog("WebSocket не открыт, отправка невозможна");
    }
  }, []);

  const reconnect = useCallback(() => {
    isRefreshingTokenRef.current = false;
    if (wsRef.current) {
      wsRef.current.close();
    }
    attemptRef.current = 0;
    connect();
  }, [connect]);

  if (!url) {
    wsLog("URL не задан, соединение не устанавливается");
    return { sendMessage: () => {}, reconnect: () => {}, isConnected: false };
  }

  return { sendMessage, reconnect, isConnected };
};

export default useWebSocket;
