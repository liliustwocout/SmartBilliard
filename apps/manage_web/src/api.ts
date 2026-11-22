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

export interface VenueSummary {
  id: number; name: string; slug: string; status: 'ACTIVE' | 'SUSPENDED'; created_at: string;
  counts: { owners: number; staff: number; customers: number };
  owner: { id: number; login: string; display_name: string; status: string; must_change_password: boolean } | null;
}
export interface Page<T> { total: number; items: T[] }
export interface CustomerRow { id: number; login: string; display_name: string; status: 'ACTIVE' | 'DISABLED'; created_at: string }
export interface AuditRow {
  id: number; at: string; actor_user_id: number | null; actor_login: string | null; venue_id: number | null; action: string; target: string | null; detail: Record<string, unknown>;
}
export interface Overview { venues: { active: number; suspended: number }; users: { owner: number; staff: number; customer: number } }
export interface CreatedVenue { venue: VenueSummary; owner_temp_password: string }

export type TableType = 'pool' | 'carom' | 'snooker' | 'other';
export interface SessionView {
  id: string; table_id: number; table_name: string | null; status: 'ACTIVE' | 'PAID' | 'VOID';
  started_at: string; ended_at: string | null; rate_snapshot: number; customer_id: number | null; void_reason: string | null;
  elapsed_seconds: number; billable_minutes: number; amount_vnd: number;
  table_amount: number; items_amount: number; items?: ItemLine[]; deposit_applied: number; amount_due: number;
}
export interface ItemLine { id: number; product_id: number; name: string; unit_price: number; quantity: number; amount: number }
export interface TableRow {
  id: number; name: string; table_type: TableType; hourly_rate: number; status: 'ACTIVE' | 'INACTIVE'; session: SessionView | null;
}
export interface TablesResponse { server_time: string; tables: TableRow[] }
export interface Revenue { date: string; total_vnd: number; session_count: number; by_table: Array<{ table_id: number; table_name: string | null; sessions: number; amount_vnd: number }> }
export type PaymentMethod = 'cash' | 'transfer';

export interface StaffRow { id: number; login: string; display_name: string; status: 'ACTIVE' | 'DISABLED'; must_change_password: boolean; created_at: string }
export interface ProductRow { id: number; name: string; price: number; status: 'ACTIVE' | 'INACTIVE' }
export interface Invoice {
  venue_name: string; invoice_no: string; table_name: string; started_at: string; ended_at: string; billable_minutes: number; rate: number;
  table_amount: number; items: ItemLine[]; items_amount: number; total: number; deposit_applied: number; amount_due: number; payment_method: PaymentMethod | null;
  cashier: string | null; customer: string | null;
}

export type BookingStatus = 'PENDING' | 'CONFIRMED' | 'CHECKED_IN' | 'CANCELLED' | 'EXPIRED' | 'NO_SHOW';
export type DepositStatus = 'PENDING' | 'PAID' | 'APPLIED' | 'REFUNDED' | 'FORFEITED' | 'CANCELLED';
export interface DepositView { amount: number; status: DepositStatus; provider: string; is_mock: boolean; applied_amount: number; refunded_amount: number }
export interface BookingView {
  id: string; table_id: number; table_name: string | null; status: BookingStatus; start_at: string; end_at: string; expires_at: string | null;
  session_id: string | null; created_at: string; deposit: DepositView | null; customer?: { id: number; name: string; phone: string };
}
export interface BookingSettings { deposit_amount: number; hold_minutes: number; refund_before_minutes: number; noshow_grace_minutes: number; payment_is_mock: boolean }
export interface Availability {
  server_time: string; settings: BookingSettings; durations: number[];
  tables: Array<{ id: number; name: string; table_type: TableType; hourly_rate: number; playing_now: boolean; busy: Array<{ start_at: string; end_at: string }> }>;
}
export interface MySession { id: string; table_name: string | null; started_at: string; ended_at: string | null; billable_minutes: number | null; total: number | null; deposit_applied: number }
export interface PublicVenue { name: string; slug: string }
