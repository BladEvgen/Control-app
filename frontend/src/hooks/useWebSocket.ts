import { log } from "../api";
import { useEffect, useRef, useCallback } from "react";

interface UseWebSocketOptions {
  url: string;
  onMessage: (event: MessageEvent) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
  shouldReconnect?: boolean;
  reconnectInterval?: number;
  pingInterval?: number;
  pongTimeout?: number;
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
}: UseWebSocketOptions) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef<boolean>(false);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRefLocal = useRef<number | null>(null);
  const attemptRef = useRef<number>(0);

  const handlePong = useCallback(() => {
    log.info("Получен pong от сервера");
    if (pongTimeoutRefLocal.current) {
      clearTimeout(pongTimeoutRefLocal.current);
      pongTimeoutRefLocal.current = null;
    }
    attemptRef.current = 0;
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      log.info("Отправка ping");
      wsRef.current.send(JSON.stringify({ type: "ping" }));

      pongTimeoutRefLocal.current = window.setTimeout(() => {
        log.warn("Не получен pong от сервера, закрытие соединения");
        wsRef.current?.close();
      }, pongTimeout);
    }
  }, [pongTimeout]);

  const connect = useCallback(() => {
    log.info("Пытаемся подключиться к WebSocket:", url);
    wsRef.current = new WebSocket(url);

    wsRef.current.onopen = () => {
      log.info("WebSocket соединение установлено");
      onOpen && onOpen();

      pingIntervalRef.current = window.setInterval(sendPing, pingInterval);

      sendPing();

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      attemptRef.current = 0;
    };

    wsRef.current.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        log.info("Получено сообщение от WebSocket:", data);

        if (data.type === "pong") {
          handlePong();
        } else {
          onMessage(event);
        }
      } catch (error) {
        log.error("Ошибка при обработке сообщения WebSocket:", error);
      }
    };

    wsRef.current.onclose = (event) => {
      log.warn("WebSocket соединение закрыто:", event);
      onClose && onClose(event);

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      if (pongTimeoutRefLocal.current) {
        clearTimeout(pongTimeoutRefLocal.current);
        pongTimeoutRefLocal.current = null;
      }

      if (shouldReconnect && isMountedRef.current) {
        const nextReconnectInterval = Math.min(
          reconnectInterval * 2 ** attemptRef.current,
          60000
        );
        log.info(
          `Пробуем переподключиться к WebSocket через ${nextReconnectInterval} мс...`
        );
        reconnectTimeoutRef.current = window.setTimeout(() => {
          attemptRef.current += 1;
          connect();
        }, nextReconnectInterval);
      }
    };

    wsRef.current.onerror = (error) => {
      log.error("Ошибка WebSocket:", error);
      onError && onError(error);
      wsRef.current?.close();
    };
  }, [
    url,
    onOpen,
    onClose,
    onError,
    onMessage,
    shouldReconnect,
    reconnectInterval,
    sendPing,
    handlePong,
    pingInterval,
    pongTimeout,
  ]);

  useEffect(() => {
    isMountedRef.current = true;
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
  }, [connect]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      log.warn("WebSocket не открыт. Невозможно отправить сообщение:", message);
    }
  }, []);

  return { sendMessage };
};

export default useWebSocket;
