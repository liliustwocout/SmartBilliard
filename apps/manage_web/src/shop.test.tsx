// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser, SessionView, TableRow } from './api';
import { duration, money } from './format';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  window.location.hash = '';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const venue = { id: 1, name: 'Quán A', slug: 'quan-a' };
const owner: AuthUser = { id: 2, role: 'owner', login: 'o', display_name: 'Chủ A', must_change_password: false, venue, csrf_token: 'tok' };
const staff: AuthUser = { ...owner, id: 3, role: 'staff', login: 's', display_name: 'Nhân viên A' };

const session: SessionView = {
  id: 'sess-1', table_id: 2, table_name: 'Bàn 2', status: 'ACTIVE', started_at: '2026-11-22T03:00:00Z', ended_at: null,
  rate_snapshot: 60000, customer_id: null, void_reason: null, elapsed_seconds: 3725, billable_minutes: 63, amount_vnd: 63000,
};
const freeTable: TableRow = { id: 1, name: 'Bàn 1', table_type: 'pool', hourly_rate: 60000, status: 'ACTIVE', session: null };
const playingTable: TableRow = { id: 2, name: 'Bàn 2', table_type: 'pool', hourly_rate: 60000, status: 'ACTIVE', session };
const inactiveTable: TableRow = { id: 3, name: 'Bàn hỏng', table_type: 'other', hourly_rate: 1, status: 'INACTIVE', session: null };

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const revenue = { date: '2026-11-22', total_vnd: 180000, session_count: 3, by_table: [] };

function mock(user: AuthUser, extra: Array<[string, (init?: RequestInit) => Response]> = [], tables: TableRow[] = [freeTable, playingTable, inactiveTable]) {
  const calls: Array<{ key: string; init?: RequestInit }> = [];
  const routes: Array<[string, (init?: RequestInit) => Response]> = [
    ['GET /api/auth/me', () => json(user)],
    ['GET /api/venues/1/tables', () => json({ server_time: 't', tables })],
    ['GET /api/venues/1/revenue/today', () => json(revenue)],
    ...extra,
  ];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    calls.push({ key, init });
    const hit = routes.find(([prefix]) => key.startsWith(prefix));
    return hit ? hit[1](init) : json({ detail: 'not mocked' }, 404);
  }));
  return calls;
}

const bodyOf = (calls: Array<{ key: string; init?: RequestInit }>, key: string) =>
  JSON.parse(String(calls.find(c => c.key === key)?.init?.body ?? 'null'));

describe('formatting', () => {
  it('formats VND and durations', () => {
    expect(money(61000)).toContain('61.000');
    expect(money(0)).toContain('0');
    expect(duration(3725)).toBe('01:02:05');
    expect(duration(-5)).toBe('00:00:00');
    expect(duration(100 * 3600)).toBe('100:00:00');
  });
});

describe('table dashboard', () => {
  it('shows free and playing tables with server amounts, hides inactive tables, and shows today revenue', async () => {
    mock(staff);
    render(<App />);
    expect(await screen.findByText('Bàn 1')).toBeTruthy();
    expect(screen.getByText('Bàn 2')).toBeTruthy();
    expect(screen.queryByText('Bàn hỏng')).toBeNull();
    expect(screen.getByText(money(63000))).toBeTruthy(); // tiền do máy chủ tính
    expect(screen.getByLabelText('Thời gian đã chơi').textContent).toMatch(/^01:02:\d\d$/);
    await waitFor(() => expect(screen.getByTestId('revenue-today').textContent).toContain('180.000'));
  });

  it('opens a table with a POST and refreshes', async () => {
    const calls = mock(staff, [['POST /api/venues/1/tables/1/open', () => json(session, 201)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Mở bàn' }));
    await waitFor(() => expect(calls.some(c => c.key === 'POST /api/venues/1/tables/1/open')).toBe(true));
    expect(await screen.findByText('Đã mở Bàn 1.')).toBeTruthy();
    expect((calls.find(c => c.key.startsWith('POST /api/venues/1/tables/1/open'))?.init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok');
  });

  it('shows the server message when the table was already opened elsewhere', async () => {
    mock(staff, [['POST /api/venues/1/tables/1/open', () => json({ detail: 'Bàn đang có phiên chơi.' }, 409)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Mở bàn' }));
    expect(await screen.findByText('Bàn đang có phiên chơi.')).toBeTruthy();
  });

  it('checkout shows the server quote and sends only the payment method', async () => {
    const paid = { ...session, status: 'PAID', amount_vnd: 64000, duplicate: false };
    const calls = mock(staff, [
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(session)],
      ['POST /api/venues/1/sessions/sess-1/checkout', () => json(paid)],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    expect((await within(dialog).findByTestId('quote-amount')).textContent).toBe(money(63000));
    fireEvent.click(within(dialog).getByLabelText('Chuyển khoản'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đã thu tiền' }));
    expect(await screen.findByText(`Đã thu ${money(64000)} · Bàn 2.`)).toBeTruthy(); // số tiền chốt lấy từ phản hồi
    expect(bodyOf(calls, 'POST /api/venues/1/sessions/sess-1/checkout')).toEqual({ payment_method: 'transfer' });
  });

  it('only the owner can void a running session, and it needs a reason', async () => {
    const calls = mock(owner, [
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(session)],
      ['POST /api/venues/1/sessions/sess-1/void', () => json({ ...session, status: 'VOID' })],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Huỷ phiên…' }));
    const confirmButton = await screen.findByRole('button', { name: 'Huỷ phiên' });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Lý do huỷ'), { target: { value: 'mở nhầm bàn' } });
    expect((screen.getByRole('button', { name: 'Huỷ phiên' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Huỷ phiên' }));
    await waitFor(() => expect(bodyOf(calls, 'POST /api/venues/1/sessions/sess-1/void')).toEqual({ reason: 'mở nhầm bàn' }));
  });

  it('staff never see the void action', async () => {
    mock(staff, [['GET /api/venues/1/sessions/sess-1/quote', () => json(session)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    expect(within(dialog).queryByRole('button', { name: 'Huỷ phiên…' })).toBeNull();
  });

  it('empty state differs for owner and staff', async () => {
    mock(owner, [], []);
    render(<App />);
    expect(await screen.findByRole('link', { name: 'Thêm bàn' })).toBeTruthy();
    cleanup();
    mock(staff, [], []);
    render(<App />);
    expect(await screen.findByText(/Nhờ chủ quán thêm bàn/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Thêm bàn' })).toBeNull();
  });
});

describe('navigation per role', () => {
  it('owner sees Bàn và giá; staff does not and is kept on the dashboard if they type the URL', async () => {
    window.location.hash = '#/tables';
    mock(staff);
    render(<App />);
    expect(await screen.findByText('Tổng quan bàn')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Bàn và giá' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Lịch sử phiên' })).toBeTruthy();
    cleanup();
    mock(owner);
    render(<App />);
    expect(await screen.findByRole('link', { name: 'Bàn và giá' })).toBeTruthy();
  });
});

describe('table management (owner)', () => {
  it('validates the hourly rate and posts a new table', async () => {
    window.location.hash = '#/tables';
    const calls = mock(owner, [['POST /api/venues/1/tables', () => json({ ...freeTable, id: 9, name: 'VIP' }, 201)]]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Thêm bàn' }))[0]);
    const dialog = await screen.findByRole('dialog', { name: 'Thêm bàn' });
    fireEvent.change(within(dialog).getByLabelText('Tên bàn'), { target: { value: 'VIP' } });
    fireEvent.change(within(dialog).getByLabelText('Giá giờ (₫)'), { target: { value: '60.5' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm bàn' }));
    expect(await within(dialog).findByText(/số nguyên từ 0 đến 10\.000\.000/)).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText('Giá giờ (₫)'), { target: { value: '80000' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm bàn' }));
    await waitFor(() => expect(bodyOf(calls, 'POST /api/venues/1/tables')).toEqual({ name: 'VIP', table_type: 'pool', hourly_rate: 80000 }));
  });

  it('cannot stop using a table that is being played', async () => {
    window.location.hash = '#/tables';
    mock(owner);
    render(<App />);
    const row = (await screen.findByText('Bàn 2')).closest('tr') as HTMLElement;
    expect((within(row).getByRole('button', { name: 'Ngừng dùng' }) as HTMLButtonElement).disabled).toBe(true);
    const free = screen.getByText('Bàn 1').closest('tr') as HTMLElement;
    expect((within(free).getByRole('button', { name: 'Ngừng dùng' }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('history', () => {
  const page = { total: 1, items: [{ ...session, status: 'PAID', ended_at: '2026-11-22T04:00:00Z', amount_vnd: 60000 }] };

  it('staff see a today-only notice and no date filters', async () => {
    window.location.hash = '#/history';
    mock(staff, [['GET /api/venues/1/sessions', () => json(page)]]);
    render(<App />);
    expect(await screen.findByText('Nhân viên chỉ xem được các phiên của hôm nay.')).toBeTruthy();
    expect(screen.queryByLabelText('Từ ngày')).toBeNull();
    expect(await within(await screen.findByRole('table')).findByText('Đã thanh toán')).toBeTruthy();
  });

  it('owner filters by date and status', async () => {
    window.location.hash = '#/history';
    const calls = mock(owner, [['GET /api/venues/1/sessions', () => json(page)]]);
    render(<App />);
    fireEvent.change(await screen.findByLabelText('Từ ngày'), { target: { value: '2026-11-01' } });
    fireEvent.change(screen.getByLabelText('Trạng thái'), { target: { value: 'PAID' } });
    await waitFor(() => expect(calls.some(c => c.key.includes('date_from=2026-11-01') && c.key.includes('status=PAID'))).toBe(true));
  });
});
