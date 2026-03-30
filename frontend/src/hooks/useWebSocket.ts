import { log } from "../api";
import { useEffect, useRef, useCallback, useState } from "react";

const WS_DEBUG = false;

const wsLog = (msg: string, data?: unknown) => {
  if (!WS_DEBUG) return;
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
  const connectionIdRef = useRef<number>(0);
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

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current != null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const clearPingTimer = useCallback(() => {
    if (pingIntervalRef.current != null) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const clearPongTimer = useCallback(() => {
    if (pongTimeoutRefLocal.current != null) {
      clearTimeout(pongTimeoutRefLocal.current);
      pongTimeoutRefLocal.current = null;
    }
  }, []);

  const isActiveSocket = useCallback(
    (socket: WebSocket | null, connectionId: number): boolean => {
      return (
        socket != null &&
        wsRef.current === socket &&
        connectionIdRef.current === connectionId
      );
    },
    [],
  );

  const handlePong = useCallback(() => {
    wsLog("pong получен");
    clearPongTimer();
    attemptRef.current = 0;
  }, [clearPongTimer]);

  const sendPing = useCallback(
    (
      socket: WebSocket | null = wsRef.current,
      connectionId: number = connectionIdRef.current,
    ) => {
      if (!isActiveSocket(socket, connectionId)) return;
      if (socket == null) return;
      if (socket.readyState !== WebSocket.OPEN) return;

      wsLog("ping отправлен");
      socket.send(JSON.stringify({ type: "ping" }));
      clearPongTimer();

      pongTimeoutRefLocal.current = window.setTimeout(() => {
        if (!isActiveSocket(socket, connectionId)) return;
        log.warn("Не получен pong от сервера, закрытие соединения");
        socket.close();
      }, pongTimeout);
    },
    [clearPongTimer, isActiveSocket, pongTimeout],
  );

  const connect = useCallback(() => {
    if (!urlRef.current) {
      wsLog("URL не задан, соединение не устанавливается");
      return;
    }
    clearReconnectTimer();
    clearPingTimer();
    clearPongTimer();
    setIsConnected(false);

    const previousSocket = wsRef.current;
    const connectionId = connectionIdRef.current + 1;
    connectionIdRef.current = connectionId;

    if (
      previousSocket &&
      (previousSocket.readyState === WebSocket.OPEN ||
        previousSocket.readyState === WebSocket.CONNECTING)
    ) {
      try {
        previousSocket.close();
      } catch {
        // ignore close errors for stale sockets
      }
    }

    wsLog("подключение", { url: urlRef.current, connectionId });
    const socket = new WebSocket(urlRef.current);
    wsRef.current = socket;

    socket.onopen = () => {
      if (!isActiveSocket(socket, connectionId)) {
        if (
          socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING
        ) {
          socket.close();
        }
        return;
      }
      wsLog("соединение установлено");
      setIsConnected(true);
      onOpenRef.current?.();

      pingIntervalRef.current = window.setInterval(() => {
        sendPing(socket, connectionId);
      }, pingInterval);

      sendPing(socket, connectionId);
      attemptRef.current = 0;
    };

    socket.onmessage = (event: MessageEvent) => {
      if (!isActiveSocket(socket, connectionId)) {
        return;
      }
      const dataStr = typeof event.data === "string" ? event.data : "";
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

        if (data.error === "token_expired" || data.action === "refresh_token") {
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
    };

    socket.onclose = (event: CloseEvent) => {
      if (!isActiveSocket(socket, connectionId)) {
        return;
      }
      wsRef.current = null;
      setIsConnected(false);
      wsLog("соединение закрыто", { code: event.code, reason: event.reason });
      clearPingTimer();
      clearPongTimer();

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
        clearReconnectTimer();
        reconnectTimeoutRef.current = window.setTimeout(() => {
          if (
            connectionIdRef.current !== connectionId ||
            wsRef.current !== null ||
            !isMountedRef.current
          ) {
            return;
          }
          attemptRef.current += 1;
          connect();
        }, nextReconnectInterval);
      }
    };

    socket.onerror = (error) => {
      if (!isActiveSocket(socket, connectionId)) {
        return;
      }
      wsLog("ошибка WebSocket", error);
      onErrorRef.current?.(error);
      socket.close();
    };
  }, [
    clearPingTimer,
    clearPongTimer,
    clearReconnectTimer,
    handlePong,
    isActiveSocket,
    pingInterval,
    reconnectInterval,
    sendPing,
    shouldReconnect,
  ]);

  useEffect(() => {
    isMountedRef.current = true;
    urlRef.current = url;
    isRefreshingTokenRef.current = false;
    connect();

    return () => {
      isMountedRef.current = false;
      clearReconnectTimer();
      clearPingTimer();
      clearPongTimer();
      connectionIdRef.current += 1;
      const socket = wsRef.current;
      wsRef.current = null;
      socket?.close();
    };
  }, [clearPingTimer, clearPongTimer, clearReconnectTimer, connect, url]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      wsLog("WebSocket не открыт, отправка невозможна");
    }
  }, []);

  const reconnect = useCallback(() => {
    isRefreshingTokenRef.current = false;
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
