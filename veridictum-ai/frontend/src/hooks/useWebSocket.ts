/**
 * VeriDictum AI — WebSocket hooks for real-time event subscriptions.
 */

import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";

const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

type EventHandler = (payload: Record<string, unknown>) => void;

function useWebSocketChannel(
  path: string,
  onMessage: EventHandler,
  enabled = true
): void {
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stableHandler = useRef(onMessage);
  stableHandler.current = onMessage;
  // Pull the access token from the auth store so we can pass it as a query
  // param. The browser WebSocket API can't set Authorization headers, so
  // this is the canonical way to authenticate a WS handshake.
  const accessToken = useAuthStore((s) => s.accessToken);

  const connect = useCallback(() => {
    if (!enabled) return;
    if (!accessToken) return; // server will reject anyway — skip the dial

    const url = `${WS_BASE}${path}?token=${encodeURIComponent(accessToken)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Start heartbeat
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 25_000);
      ws.onclose = () => {
        clearInterval(ping);
        // Reconnect after 3 seconds
        retryRef.current = setTimeout(connect, 3_000);
      };
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        stableHandler.current(data);
      } catch {
        // ignore non-JSON (e.g. "pong")
      }
    };

    ws.onerror = () => ws.close();
  }, [path, enabled, accessToken]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, [connect]);
}


/** Subscribe to all real-time events for a case (transcription, OCR, analysis). */
export function useCaseEvents(
  caseId: string | undefined,
  onEvent?: EventHandler
): void {
  const queryClient = useQueryClient();

  const handleMessage = useCallback(
    (payload: Record<string, unknown>) => {
      const event = payload.event as string | undefined;

      // Invalidate relevant queries so UI refreshes automatically
      if (event === "transcript_ready") {
        queryClient.invalidateQueries({ queryKey: ["audio", caseId] });
        queryClient.invalidateQueries({ queryKey: ["transcripts", caseId] });
      } else if (event === "ocr_complete") {
        queryClient.invalidateQueries({ queryKey: ["documents", caseId] });
      } else if (event === "analysis_complete") {
        queryClient.invalidateQueries({ queryKey: ["contradictions", caseId] });
        queryClient.invalidateQueries({ queryKey: ["contradiction-stats", caseId] });
        queryClient.invalidateQueries({ queryKey: ["analysis-jobs", caseId] });
      }

      onEvent?.(payload);
    },
    [caseId, queryClient, onEvent]
  );

  useWebSocketChannel(
    caseId ? `/ws/cases/${caseId}` : "",
    handleMessage,
    !!caseId
  );
}


/** Subscribe to real-time status updates for a specific analysis job. */
export function useJobStatus(
  jobId: string | undefined,
  onUpdate?: (status: string, progress: number, total: number) => void
): void {
  const queryClient = useQueryClient();

  const handleMessage = useCallback(
    (payload: Record<string, unknown>) => {
      if (payload.event !== "job_update") return;
      const status = payload.status as string;
      const progress = (payload.progress as number) ?? 0;
      const total = (payload.total_contradictions_found as number) ?? 0;
      onUpdate?.(status, progress, total);

      if (status === "COMPLETE" || status === "FAILED") {
        queryClient.invalidateQueries({ queryKey: ["analysis-jobs"] });
        queryClient.invalidateQueries({ queryKey: ["contradictions"] });
      }
    },
    [jobId, queryClient, onUpdate]
  );

  useWebSocketChannel(
    jobId ? `/ws/jobs/${jobId}` : "",
    handleMessage,
    !!jobId
  );
}


/** Subscribe to real-time in-app notifications for the current user. */
export function useUserNotifications(
  userId: string | undefined,
  onNotification?: (payload: Record<string, unknown>) => void
): void {
  const queryClient = useQueryClient();

  const handleMessage = useCallback(
    (payload: Record<string, unknown>) => {
      if (payload.event !== "notification") return;
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["unread-count"] });
      onNotification?.(payload);
    },
    [userId, queryClient, onNotification]
  );

  useWebSocketChannel(
    userId ? `/ws/users/${userId}` : "",
    handleMessage,
    !!userId
  );
}
