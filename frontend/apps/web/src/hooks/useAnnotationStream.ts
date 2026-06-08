import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { API_BASE_URL } from "@/api/client";
import { annotationKeys } from "@/hooks/useAnnotations";

export type AnnotationStreamStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

export type AnnotationEvent = {
  type: string;
  query_id?: number;
  data?: unknown;
  timestamp?: string;
};

const INVALIDATE_DEBOUNCE_MS = 180;
const INACTIVITY_TIMEOUT_MS = 75_000;
const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000] as const;
const INVALIDATING_EVENT_TYPES = new Set([
  "annotation.created",
  "annotation.deleted",
  "annotation.batch_created",
  "annotations.deleted",
]);

export function useAnnotationStream(queryId: number | null): {
  status: AnnotationStreamStatus;
  lastEvent: AnnotationEvent | null;
  reconnect: () => void;
} {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AnnotationStreamStatus>(
    queryId === null ? "idle" : "connecting",
  );
  const [lastEvent, setLastEvent] = useState<AnnotationEvent | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const invalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const generationRef = useRef(0);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const clearInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current !== null) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
  }, []);

  const clearInvalidateTimer = useCallback(() => {
    if (invalidateTimerRef.current !== null) {
      clearTimeout(invalidateTimerRef.current);
      invalidateTimerRef.current = null;
    }
  }, []);

  const scheduleInvalidate = useCallback(
    (activeQueryId: number) => {
      clearInvalidateTimer();
      invalidateTimerRef.current = setTimeout(() => {
        invalidateTimerRef.current = null;
        void queryClient.invalidateQueries({
          queryKey: annotationKeys.query(activeQueryId),
        });
      }, INVALIDATE_DEBOUNCE_MS);
    },
    [clearInvalidateTimer, queryClient],
  );

  const closeSocket = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    if (
      socket !== null &&
      (socket.readyState === WebSocket.CONNECTING ||
        socket.readyState === WebSocket.OPEN)
    ) {
      socket.close();
    }
  }, []);

  const connect = useCallback(
    (activeQueryId: number, generation: number) => {
      const currentSocket = socketRef.current;
      if (
        currentSocket !== null &&
        (currentSocket.readyState === WebSocket.CONNECTING ||
          currentSocket.readyState === WebSocket.OPEN)
      ) {
        return;
      }

      setStatus(reconnectAttemptRef.current === 0 ? "connecting" : "reconnecting");

      const socket = new WebSocket(getAnnotationWebSocketUrl(activeQueryId));
      socketRef.current = socket;

      const resetInactivityTimer = () => {
        clearInactivityTimer();
        inactivityTimerRef.current = setTimeout(() => {
          if (generationRef.current !== generation || socketRef.current !== socket) {
            return;
          }
          socket.close();
        }, INACTIVITY_TIMEOUT_MS);
      };

      const scheduleReconnect = () => {
        if (generationRef.current !== generation) {
          return;
        }
        clearInactivityTimer();
        socketRef.current = null;

        const attempt = reconnectAttemptRef.current;
        if (attempt >= RECONNECT_DELAYS_MS.length) {
          setStatus("disconnected");
          return;
        }

        setStatus("reconnecting");
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          reconnectAttemptRef.current = attempt + 1;
          connect(activeQueryId, generation);
        }, RECONNECT_DELAYS_MS[attempt]);
      };

      socket.onopen = () => {
        if (generationRef.current !== generation) {
          socket.close();
          return;
        }
        reconnectAttemptRef.current = 0;
        setStatus("connected");
        resetInactivityTimer();
      };

      socket.onmessage = (event) => {
        if (generationRef.current !== generation) {
          return;
        }
        resetInactivityTimer();
        const parsed = parseAnnotationEvent(event.data);
        if (parsed === null) {
          return;
        }
        if (parsed.type === "ping") {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "pong" }));
          }
          return;
        }
        if (parsed.query_id !== undefined && parsed.query_id !== activeQueryId) {
          return;
        }

        setLastEvent(parsed);
        if (INVALIDATING_EVENT_TYPES.has(parsed.type)) {
          scheduleInvalidate(activeQueryId);
        }
      };

      socket.onerror = () => {
        if (generationRef.current === generation) {
          setStatus("error");
        }
      };

      socket.onclose = () => {
        if (generationRef.current !== generation) {
          return;
        }
        scheduleReconnect();
      };
    },
    [clearInactivityTimer, scheduleInvalidate],
  );

  const reconnect = useCallback(() => {
    clearReconnectTimer();
    clearInactivityTimer();
    generationRef.current += 1;
    reconnectAttemptRef.current = 0;
    closeSocket();
    if (queryId === null) {
      setStatus("idle");
      return;
    }
    connect(queryId, generationRef.current);
  }, [clearInactivityTimer, clearReconnectTimer, closeSocket, connect, queryId]);

  useEffect(() => {
    clearReconnectTimer();
    clearInactivityTimer();
    closeSocket();
    reconnectAttemptRef.current = 0;
    generationRef.current += 1;

    if (queryId === null) {
      setStatus("idle");
      setLastEvent(null);
      return undefined;
    }

    const generation = generationRef.current;
    connect(queryId, generation);

    return () => {
      generationRef.current += 1;
      clearReconnectTimer();
      clearInactivityTimer();
      closeSocket();
    };
  }, [clearInactivityTimer, clearReconnectTimer, closeSocket, connect, queryId]);

  useEffect(
    () => () => {
      clearInvalidateTimer();
    },
    [clearInvalidateTimer],
  );

  return { status, lastEvent, reconnect };
}

export function getAnnotationWebSocketUrl(queryId: number): string {
  const base = new URL(API_BASE_URL, window.location.origin);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${base.host}/ws/queries/${queryId}/annotations`;
}

function parseAnnotationEvent(value: unknown): AnnotationEvent | null {
  if (typeof value !== "string") {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(value);
    if (!isRecord(parsed) || typeof parsed.type !== "string") {
      return null;
    }
    return {
      type: parsed.type,
      query_id: typeof parsed.query_id === "number" ? parsed.query_id : undefined,
      data: parsed.data,
      timestamp: typeof parsed.timestamp === "string" ? parsed.timestamp : undefined,
    };
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
