// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { Availability, AuthUser, BookingView } from './api';
import { addDays, clockLabel, slotIso, todayVN } from './format';
import { parseRoute } from './pages/AppShell';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-22T03:00:00Z')); // 10:00 giờ Việt Nam
  window.location.hash = '';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const venue = { id: 1, name: 'Quán A', slug: 'quan-a' };
const customer: AuthUser = { id: 9, role: 'customer', login: '0901111111', display_name: 'Anh Nam', must_change_password: false, venue, csrf_token: 'tok' };
const staff: AuthUser = { ...customer, id: 3, role: 'staff', login: 's', display_name: 'Thu ngân' };
const owner: AuthUser = { ...staff, id: 2, role: 'owner', login: 'o', display_name: 'Chủ A' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

type Route = [string, (init?: RequestInit) => Response];
function mock(routes: Route[]) {
  const calls: Array<{ key: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    calls.push({ key, init });
    const hit = routes.find(([prefix]) => key.startsWith(prefix));
    return hit ? hit[1](init) : json({ detail: 'not mocked' }, 404);
  }));
  return calls;
}
const bodyOf = (calls: Array<{ key: string; init?: RequestInit }>, key: string) => JSON.parse(String(calls.find(c => c.key === key)?.init?.body ?? 'null'));

const settings = { deposit_amount: 50000, hold_minutes: 15, refund_before_minutes: 60, noshow_grace_minutes: 30, payment_is_mock: true };
const availability: Availability = {
  server_time: '2026-11-22T03:00:00Z', settings, durations: [30, 60, 90],
  tables: [
    { id: 1, name: 'Bàn 1', table_type: 'pool', hourly_rate: 60000, playing_now: false, busy: [{ start_at: '2026-11-22T07:00:00Z', end_at: '2026-11-22T08:00:00Z' }] }, // 14:00-15:00 VN bận
    { id: 2, name: 'Bàn VIP', table_type: 'carom', hourly_rate: 120000, playing_now: true, busy: [] },
  ],
};
const pending: BookingView = {
  id: 'b-1', table_id: 1, table_name: 'Bàn 1', status: 'PENDING', start_at: '2026-11-22T05:00:00Z', end_at: '2026-11-22T06:00:00Z',
  expires_at: '2026-11-22T03:15:00Z', session_id: null, created_at: 't', deposit: { amount: 50000, status: 'PENDING', provider: 'mock', is_mock: true, applied_amount: 0, refunded_amount: 0 },
};

describe('helpers', () => {
  it('uses Vietnam time for dates and slots', () => {
    expect(todayVN()).toBe('2026-11-22');
    expect(todayVN(new Date('2026-11-22T20:00:00Z').getTime())).toBe('2026-11-23'); // 03:00 ngày 23 giờ VN
    expect(slotIso('2026-11-22', 14 * 60)).toBe('2026-11-22T07:00:00.000Z');
    expect(addDays('2026-11-30', 1)).toBe('2026-12-01');
    expect(addDays('2026-11-22', 14)).toBe('2026-12-06');
    expect(clockLabel(570)).toBe('09:30');
  });

  it('parses customer entry routes', () => {
    expect(parseRoute('#/c/quan-a')).toEqual({ name: 'customer-entry', slug: 'quan-a' });
    expect(parseRoute('#/c/Quan A!')).toEqual({ name: 'home' });
    expect(parseRoute('#/my/bookings')).toEqual({ name: 'my-bookings' });
    expect(parseRoute('#/bookings')).toEqual({ name: 'bookings' });
  });
});

describe('customer entry page', () => {
  const anon: Route = ['GET /api/auth/me', () => json({ detail: 'x' }, 401)];

  it('shows the venue and validates before registering, then registers for that venue', async () => {
    window.location.hash = '#/c/quan-a';
    const calls = mock([anon, ['GET /api/public/venues/quan-a', () => json({ name: 'Quán A', slug: 'quan-a' })],
      ['POST /api/auth/register', () => json(customer, 201)],
      ['GET /api/venues/1/availability', () => json(availability)]]);
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Quán A' })).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Đăng ký' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tạo tài khoản' }));
    expect(await screen.findByText('Nhập đủ tên, số điện thoại và mật khẩu.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Tên của bạn'), { target: { value: 'Anh Nam' } });
    fireEvent.change(screen.getByLabelText('Số điện thoại'), { target: { value: '0901111111' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'Khach-Hang-2026' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo tài khoản' }));
    expect(await screen.findByRole('heading', { name: 'Đặt bàn' })).toBeTruthy();
    expect(bodyOf(calls, 'POST /api/auth/register')).toEqual({ venue_slug: 'quan-a', display_name: 'Anh Nam', phone: '0901111111', password: 'Khach-Hang-2026' });
    expect(screen.queryByRole('link', { name: 'Nhân viên' })).toBeNull(); // khách không có menu vận hành
  });

  it('logs in with the venue slug and shows server errors', async () => {
    window.location.hash = '#/c/quan-a';
    const calls = mock([anon, ['GET /api/public/venues/quan-a', () => json({ name: 'Quán A', slug: 'quan-a' })],
      ['POST /api/auth/login', () => json({ detail: 'Sai tài khoản hoặc mật khẩu.' }, 401)]]);
    render(<App />);
    await screen.findByRole('heading', { name: 'Quán A' });
    fireEvent.change(screen.getByLabelText('Số điện thoại'), { target: { value: '0901111111' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'sai' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText('Sai tài khoản hoặc mật khẩu.')).toBeTruthy();
    expect(bodyOf(calls, 'POST /api/auth/login').venue_slug).toBe('quan-a');
  });

  it('explains an unknown or suspended venue', async () => {
    window.location.hash = '#/c/khong-co';
    mock([anon, ['GET /api/public/venues/khong-co', () => json({ detail: 'Không tìm thấy quán.' }, 404)]]);
    render(<App />);
    expect(await screen.findByText('Địa chỉ quán không đúng hoặc quán đang tạm ngưng.')).toBeTruthy();
  });
});

describe('booking a table', () => {
  const base: Route[] = [['GET /api/auth/me', () => json(customer)], ['GET /api/venues/1/availability', () => json(availability)]];

  it('disables past and busy slots, and shows the mock deposit notice', async () => {
    mock(base);
    render(<App />);
    expect(await screen.findByText(/chế độ mô phỏng/)).toBeTruthy();
    const slots = await screen.findByRole('radiogroup', { name: 'Giờ bắt đầu' });
    const slot = (label: string) => within(slots).getByRole('radio', { name: label }) as HTMLButtonElement;
    expect(within(slots).queryByRole('radio', { name: '09:30' })).toBeNull(); // giờ đã qua (10:00 hiện tại) không hiện
    expect(slot('10:30').disabled).toBe(false);
    expect(slot('14:00').disabled).toBe(true); // bàn đã có người đặt 14:00–15:00
    expect(slot('13:30').disabled).toBe(true); // 13:30–14:30 chồng với 14:00–15:00
    expect(slot('13:00').disabled).toBe(false); // 13:00–14:00 sát giờ, không chồng
  });

  it('a longer duration also blocks slots that would run into a busy period', async () => {
    mock(base);
    render(<App />);
    const slots = await screen.findByRole('radiogroup', { name: 'Giờ bắt đầu' });
    expect((within(slots).getByRole('radio', { name: '13:00' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('Thời lượng'), { target: { value: '90' } });
    expect((within(slots).getByRole('radio', { name: '13:00' }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(slots).getByRole('radio', { name: '12:30' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('radio', { name: /Bàn VIP/ }));
    expect((within(slots).getByRole('radio', { name: '14:00' }) as HTMLButtonElement).disabled).toBe(false); // bàn khác không bận
  });

  it('creates a booking, then pays the mock deposit', async () => {
    const calls = mock([...base,
      ['POST /api/venues/1/my/bookings/b-1/deposit/mock-pay', () => json({ ...pending, status: 'CONFIRMED', expires_at: null, deposit: { ...pending.deposit!, status: 'PAID' } })],
      ['POST /api/venues/1/my/bookings', () => json(pending, 201)]]);
    render(<App />);
    const slots = await screen.findByRole('radiogroup', { name: 'Giờ bắt đầu' });
    fireEvent.click(within(slots).getByRole('radio', { name: '12:00' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tiếp tục' }));
    const confirm = await screen.findByRole('dialog', { name: 'Xác nhận đặt bàn' });
    fireEvent.click(within(confirm).getByRole('button', { name: 'Đặt bàn và trả cọc' }));
    expect(bodyOf(calls, 'POST /api/venues/1/my/bookings') ?? await waitFor(() => bodyOf(calls, 'POST /api/venues/1/my/bookings'))).toEqual(
      { table_id: 1, start_at: '2026-11-22T05:00:00.000Z', duration_minutes: 60 });
    const deposit = await screen.findByRole('dialog', { name: 'Trả tiền cọc' });
    expect(within(deposit).getByText(/không có khoản tiền thật/)).toBeTruthy();
    expect(within(deposit).getByTestId('deposit-amount').textContent).toContain('50.000');
    fireEvent.click(within(deposit).getByRole('button', { name: 'Trả cọc (mô phỏng)' }));
    expect(await screen.findByText('Đã xác nhận lịch đặt.')).toBeTruthy();
  });

  it('shows the server conflict message when someone else took the slot', async () => {
    mock([...base, ['POST /api/venues/1/my/bookings', () => json({ detail: 'Bàn đã có người đặt trong khung giờ này. Hãy chọn giờ hoặc bàn khác.' }, 409)]]);
    render(<App />);
    const slots = await screen.findByRole('radiogroup', { name: 'Giờ bắt đầu' });
    fireEvent.click(within(slots).getByRole('radio', { name: '11:00' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tiếp tục' }));
    const confirm = await screen.findByRole('dialog', { name: 'Xác nhận đặt bàn' });
    fireEvent.click(within(confirm).getByRole('button', { name: 'Đặt bàn và trả cọc' }));
    expect(await within(confirm).findByText(/Bàn đã có người đặt/)).toBeTruthy();
  });
});

describe('my bookings', () => {
  const confirmed: BookingView = { ...pending, id: 'b-2', status: 'CONFIRMED', expires_at: null, deposit: { ...pending.deposit!, status: 'PAID' } };

  it('lists bookings with deposit state and lets the customer pay a pending one', async () => {
    window.location.hash = '#/my/bookings';
    const calls = mock([['GET /api/auth/me', () => json(customer)], ['GET /api/venues/1/booking-settings', () => json(settings)],
      ['GET /api/venues/1/my/bookings', () => json([pending, confirmed])],
      ['POST /api/venues/1/my/bookings/b-1/deposit/mock-pay', () => json(confirmed)]]);
    render(<App />);
    expect(await screen.findByText('Chờ trả cọc')).toBeTruthy();
    expect(screen.getByText('Đã xác nhận')).toBeTruthy();
    expect(screen.getAllByText(/\(mô phỏng\)/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Trả cọc' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Trả cọc (mô phỏng)' }));
    await waitFor(() => expect(calls.some(c => c.key === 'POST /api/venues/1/my/bookings/b-1/deposit/mock-pay')).toBe(true));
  });

  it('warns about losing the deposit when cancelling too late, and about the refund otherwise', async () => {
    window.location.hash = '#/my/bookings';
    const soon = { ...confirmed, id: 'b-3', start_at: '2026-11-22T03:30:00Z', end_at: '2026-11-22T04:30:00Z' }; // còn 30 phút
    const calls = mock([['GET /api/auth/me', () => json(customer)], ['GET /api/venues/1/booking-settings', () => json(settings)],
      ['GET /api/venues/1/my/bookings', () => json([soon, confirmed])],
      ['POST /api/venues/1/my/bookings/b-3/cancel', () => json({ ...soon, status: 'CANCELLED' })]]);
    render(<App />);
    const buttons = await screen.findAllByRole('button', { name: 'Huỷ lịch' });
    fireEvent.click(buttons[0]);
    expect(await screen.findByText(/sẽ mất cọc/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Huỷ lịch đặt' }));
    await waitFor(() => expect(calls.some(c => c.key === 'POST /api/venues/1/my/bookings/b-3/cancel')).toBe(true));
    cleanup();
    mock([['GET /api/auth/me', () => json(customer)], ['GET /api/venues/1/booking-settings', () => json(settings)], ['GET /api/venues/1/my/bookings', () => json([confirmed])]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Huỷ lịch' }));
    expect(await screen.findByText(/được hoàn cọc/)).toBeTruthy();
  });

  it('shows an empty state without bookings', async () => {
    window.location.hash = '#/my/bookings';
    mock([['GET /api/auth/me', () => json(customer)], ['GET /api/venues/1/booking-settings', () => json(settings)], ['GET /api/venues/1/my/bookings', () => json([])]]);
    render(<App />);
    expect(await screen.findByText('Bạn chưa đặt bàn nào')).toBeTruthy();
  });
});

describe('counter: bookings and deposit rules', () => {
  const row: BookingView = { ...pending, id: 'b-9', status: 'CONFIRMED', deposit: { ...pending.deposit!, status: 'PAID' }, customer: { id: 9, name: 'Anh Nam', phone: '0901111111' } };

  it('staff see bookings, can check a customer in, but cannot edit the deposit rules', async () => {
    window.location.hash = '#/bookings';
    const calls = mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/bookings', () => json([row])],
      ['POST /api/venues/1/bookings/b-9/check-in', () => json({ booking: row, session_id: 's-1' })]]);
    render(<App />);
    expect(await screen.findByText('Anh Nam · 0901111111')).toBeTruthy();
    expect(screen.queryByText('Luật đặt bàn và tiền cọc')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Nhận bàn' }));
    const dialog = await screen.findByRole('dialog', { name: 'Nhận bàn cho khách?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Nhận bàn' }));
    await waitFor(() => expect(calls.some(c => c.key === 'POST /api/venues/1/bookings/b-9/check-in')).toBe(true));
  });

  it('owner edits the rules with validation', async () => {
    window.location.hash = '#/bookings';
    const calls = mock([['GET /api/auth/me', () => json(owner)], ['GET /api/venues/1/bookings', () => json([])],
      ['GET /api/venues/1/booking-settings', () => json(settings)], ['PUT /api/venues/1/booking-settings', () => json(settings)]]);
    render(<App />);
    const deposit = await screen.findByLabelText('Tiền cọc mỗi lượt (₫)');
    fireEvent.change(deposit, { target: { value: '-5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu luật đặt bàn' }));
    expect(await screen.findByText('Nhập số nguyên không âm.')).toBeTruthy();
    fireEvent.change(deposit, { target: { value: '80000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu luật đặt bàn' }));
    await waitFor(() => expect(bodyOf(calls, 'PUT /api/venues/1/booking-settings').deposit_amount).toBe(80000));
  });
});

describe('checkout with a deposit', () => {
  it('shows the deposit deduction and collects only the amount due', async () => {
    const table = { id: 2, name: 'Bàn 2', table_type: 'pool', hourly_rate: 60000, status: 'ACTIVE', session: {
      id: 'sess-1', table_id: 2, table_name: 'Bàn 2', status: 'ACTIVE', started_at: 't', ended_at: null, rate_snapshot: 60000, customer_id: 9, void_reason: null,
      elapsed_seconds: 7200, billable_minutes: 120, table_amount: 120000, items_amount: 0, amount_vnd: 120000, deposit_applied: 50000, voucher_discount: 0, amount_due: 70000 } };
    mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [table] })],
      ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })],
      ['GET /api/venues/1/sessions/sess-1/quote', () => json({ ...table.session, items: [] })],
      ['GET /api/venues/1/products', () => json([])], ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    expect((await within(dialog).findByTestId('quote-total')).textContent).toContain('120.000');
    expect(within(dialog).getByTestId('deposit-applied').textContent).toContain('50.000');
    expect(within(dialog).getByTestId('quote-amount').textContent).toContain('70.000');
  });
});
