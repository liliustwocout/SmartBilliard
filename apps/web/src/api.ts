import { useEffect, useState } from 'react';
import type { Snapshot } from './types';

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Yêu cầu thất bại (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function useDashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState(false);
  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    let reconnect: ReturnType<typeof setTimeout>;
    let lastMessage = Date.now();
    const update = (next: Snapshot) => {
      if (!closed) setSnapshot(old => !old || next.server_time >= old.server_time ? next : old);
    };
    request<Snapshot>('/dashboard').then(update).catch(() => {});
    function connect() {
      if (closed) return;
      lastMessage = Date.now();
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
      socket.onmessage = event => {
        try {
          const next = JSON.parse(event.data) as Snapshot;
          if (next.type === 'snapshot') {
            lastMessage = Date.now();
            setOnline(true);
            update(next);
          }
        } catch { socket?.close(); }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!closed) {
          setOnline(false);
          reconnect = setTimeout(connect, 1500);
        }
      };
    }
    connect();
    const watchdog = setInterval(() => {
      if (Date.now() - lastMessage > 5000) {
        setOnline(false);
        socket?.close();
      }
    }, 2000);
    return () => { closed = true; clearTimeout(reconnect); clearInterval(watchdog); socket?.close(); };
  }, []);
  return { snapshot, online };
}
