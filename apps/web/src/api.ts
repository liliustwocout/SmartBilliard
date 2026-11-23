import { useEffect, useState } from 'react';
import type { Snapshot } from './types';

export async function request<T>(path: string, body?: unknown, timeoutMs = 25000): Promise<T> {
  try {
    const response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : `Yêu cầu thất bại (${response.status})`);
    }
    return response.json() as Promise<T>;
  } catch (err: unknown) {
    const e = err as Error;
    if (e.name === 'AbortError' || e.name === 'TimeoutError' || (e.message && e.message.toLowerCase().includes('timed out'))) {
      throw new Error('Máy chủ đang bận xử lý hoặc phản hồi quá thời gian chờ. Vui lòng thử lại sau giây lát.');
    }
    throw err;
  }
}

export async function uploadVideoFile<T>(
  file: File,
  options: { autoStart?: boolean; autoEvaluate?: boolean } = {},
  timeoutMs = 300000,
): Promise<T> {
  const params = new URLSearchParams({
    filename: file.name || 'upload.mp4',
    auto_start: String(options.autoStart ?? true),
    auto_evaluate: String(options.autoEvaluate ?? true),
  });
  const response = await fetch(`/api/videos/upload?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Tải video thất bại (${response.status})`);
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
