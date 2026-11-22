export interface Health { status: string; app: string; time: string }

export type Role = 'platform_admin' | 'owner' | 'staff' | 'customer';
export interface AuthUser {
  id: number; role: Role; login: string; display_name: string; must_change_password: boolean;
  venue: { id: number; name: string; slug: string } | null; csrf_token: string;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

let csrfToken = '';
export const setCsrfToken = (token: string) => { csrfToken = token; };

export async function api<T>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const method = options.method ?? (options.body === undefined ? 'GET' : 'POST');
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken;
  const response = await fetch(`/api${path}`, {
    method, headers, credentials: 'same-origin',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(options.timeoutMs ?? 8000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(typeof error.detail === 'string' ? error.detail : `Yêu cầu thất bại (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export async function fetchHealth(timeoutMs = 5000): Promise<Health> {
  const body = await api<Health>('/health', { timeoutMs });
  if (body.app !== 'manage') throw new Error('Đang kết nối nhầm máy chủ (không phải phòng quản lý)');
  return body;
}
