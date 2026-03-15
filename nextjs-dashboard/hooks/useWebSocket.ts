'use client';
import { useEffect, useRef, useCallback, useState } from 'react';

export type WSEvent = {
  type: 'bot_status_change' | 'new_approval' | 'new_activity' | 'task_complete' | 'stats_update';
  data: Record<string, unknown>;
};

export function useWebSocket(onEvent: (e: WSEvent) => void) {
  const wsRef    = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws/live');
      wsRef.current = ws;

      ws.onopen  = () => { setConnected(true); };
      ws.onclose = () => {
        setConnected(false);
        retryRef.current = setTimeout(connect, 3000);
      };
      ws.onerror = () => { ws.close(); };
      ws.onmessage = (msg) => {
        try { onEvent(JSON.parse(msg.data) as WSEvent); } catch {}
      };
    } catch {
      retryRef.current = setTimeout(connect, 3000);
    }
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
