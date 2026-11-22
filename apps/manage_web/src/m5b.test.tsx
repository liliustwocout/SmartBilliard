// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser, GameState } from './api';
import { toBp, totalBp } from './pages/shop/GamePage';
import { parseRoute } from './pages/AppShell';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduced-motion'), media: query, addEventListener() {}, removeEventListener() {} }));
  window.location.hash = '';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

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

const days = Array.from({ length: 14 }, (_, i) => ({ day: `2026-11-${String(9 + i).padStart(2, '0')}`, checked: i >= 11 }));
const prizes = [
  { id: 1, name: '+20 điểm', kind: 'points' as const, value: 20, percent: 40 },
  { id: 2, name: 'Giảm 10.000₫', kind: 'discount_vnd' as const, value: 10000, percent: 10 },
  { id: 3, name: 'Chúc may mắn', kind: 'nothing' as const, value: 0, percent: 50 },
];
const game: GameState = {
  points: 130, level: { name: 'Bạc', next_at: 500 }, streak: 3, best_streak: 5, checked_in_today: false, checkin_mode: 'wifi', checkin_points: 10, needs_code: false,
  calendar: days, next_milestone: { days: 7, bonus: 50 }, tickets: [{ id: 41, day: '2026-11-22', expires_at: 't' }],
  wheel: { enabled: true, prizes, daily_guarantee: true },
  vouchers: [{ id: 5, code: 'ABCD2345', label: 'Giảm 10.000₫', kind: 'discount_vnd', value: 10000, expires_at: '2026-12-22T03:00:00Z' }],
  ledger: [{ delta: 10, reason: 'checkin', at: '2026-11-22T03:00:00Z' }],
};
const me: Route = ['GET /api/auth/me', () => json(customer)];

describe('helpers and routes', () => {
  it('converts percent to basis points without float drift', () => {
    expect(toBp('12.5')).toBe(1250);
    expect(toBp('0.07')).toBe(7);
    expect(totalBp([{ name: 'a', kind: 'points', value: '1', percent: '33.33', stock: '', days: '30' }, { name: 'b', kind: 'nothing', value: '0', percent: '66.67', stock: '', days: '30' }])).toBe(10000);
    expect(parseRoute('#/my/rewards')).toEqual({ name: 'my-rewards' });
    expect(parseRoute('#/game')).toEqual({ name: 'game' });
    expect(parseRoute('#/checkin-code')).toEqual({ name: 'checkin-code' });
  });
});

describe('customer rewards page', () => {
  beforeEach(() => { window.location.hash = '#/my/rewards'; });

  it('shows points, level, streak, calendar, odds and vouchers', async () => {
    mock([me, ['GET /api/venues/1/my/game', () => json(game)]]);
    render(<App />);
    expect((await screen.findByTestId('points')).textContent).toBe('130');
    expect(screen.getByText('Hạng Bạc')).toBeTruthy();
    expect(screen.getByTestId('streak').textContent).toContain('3 ngày');
    expect(screen.getByText(/Check-in 7 ngày liên tiếp để nhận thêm \+50 điểm/)).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('26');
    expect(screen.getAllByLabelText(/đã check-in/).length).toBe(3);
    expect(screen.getByText('Quán đảm bảo mỗi ngày có phần thưởng cho khách quay. Phần thưởng chỉ dùng tại quán, không quy đổi thành tiền.')).toBeTruthy();
    expect(screen.getByText('40%')).toBeTruthy();
    expect(screen.getByTestId('voucher-code').textContent).toBe('ABCD2345');
    expect(screen.getByRole('link', { name: 'Quà tặng' }).getAttribute('aria-current')).toBe('page');
  });

  it('checks in, shows the server error when not on the venue wifi, and shows the done state', async () => {
    const calls = mock([me, ['GET /api/venues/1/my/game', () => json(game)],
      ['POST /api/venues/1/my/checkin', () => json({ detail: 'Bạn cần kết nối wifi của quán để check-in.' }, 403)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Check-in \(\+10 điểm\)/ }));
    expect(await screen.findByText('Bạn cần kết nối wifi của quán để check-in.')).toBeTruthy();
    expect(bodyOf(calls, 'POST /api/venues/1/my/checkin')).toEqual({ code: null });
    cleanup();
    mock([me, ['GET /api/venues/1/my/game', () => json({ ...game, checked_in_today: true })]]);
    render(<App />);
    expect(await screen.findByText(/Bạn đã check-in hôm nay/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Check-in \(\+10/ })).toBeNull();
  });

  it('asks for the counter code in code mode and sends it upper-cased', async () => {
    const calls = mock([me, ['GET /api/venues/1/my/game', () => json({ ...game, checkin_mode: 'code', needs_code: true })],
      ['POST /api/venues/1/my/checkin', () => json({ already_checked_in: false, points_added: 10, streak: 4, ticket_id: 42 })]]);
    render(<App />);
    fireEvent.change(await screen.findByLabelText('Mã check-in tại quầy'), { target: { value: 'ab3k9z' } });
    fireEvent.click(screen.getByRole('button', { name: /Check-in \(\+10 điểm\)/ }));
    await waitFor(() => expect(bodyOf(calls, 'POST /api/venues/1/my/checkin')).toEqual({ code: 'AB3K9Z' }));
    expect(await screen.findByText(/Check-in thành công: \+10 điểm và 1 lượt quay/)).toBeTruthy();
  });

  it('spins using the server result: the wheel lands on the server index and the prize is revealed', async () => {
    const calls = mock([me, ['GET /api/venues/1/my/game', () => json(game)],
      ['POST /api/venues/1/my/spins/41/spin', () => json({ duplicate: false, prize: { id: 2, name: 'Giảm 10.000₫', kind: 'discount_vnd', value: 10000 }, prize_index: 1,
        voucher: { code: 'WXYZ7788', label: 'Giảm 10.000₫', expires_at: '2026-12-22T03:00:00Z' }, points: 130 })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Quay (1 lượt)' }));
    await waitFor(() => expect(calls.some(c => c.key === 'POST /api/venues/1/my/spins/41/spin')).toBe(true));
    expect((await screen.findByTestId('prize-result')).textContent).toBe('Giảm 10.000 ₫');
    expect(screen.getByText('WXYZ7788')).toBeTruthy();
    const disc = document.querySelector('.wheel-disc') as SVGElement;
    expect(disc.getAttribute('style')).toContain('rotate(180deg)'); // ô thứ 2/3: 360 − 1,5 × 120, giảm chuyển động nên không quay thêm vòng
  });

  it('shows "no luck" results kindly and explains missing tickets and a disabled wheel', async () => {
    mock([me, ['GET /api/venues/1/my/game', () => json(game)],
      ['POST /api/venues/1/my/spins/41/spin', () => json({ duplicate: false, prize: { id: 3, name: 'Chúc may mắn', kind: 'nothing', value: 0 }, prize_index: 2, voucher: null, points: 130 })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Quay (1 lượt)' }));
    expect(await screen.findByText('Lần này chưa may mắn')).toBeTruthy();
    cleanup();
    mock([me, ['GET /api/venues/1/my/game', () => json({ ...game, tickets: [] })]]);
    render(<App />);
    expect(await screen.findByText(/Bạn chưa có lượt quay/)).toBeTruthy();
    cleanup();
    mock([me, ['GET /api/venues/1/my/game', () => json({ ...game, wheel: { enabled: false, prizes: [], daily_guarantee: false } })]]);
    render(<App />);
    expect(await screen.findByText('Vòng quay của quán đang tạm tắt.')).toBeTruthy();
  });

  it('shows the server message when a ticket cannot be spun', async () => {
    mock([me, ['GET /api/venues/1/my/game', () => json(game)], ['POST /api/venues/1/my/spins/41/spin', () => json({ detail: 'Lượt quay đã hết hạn.' }, 409)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Quay (1 lượt)' }));
    expect(await screen.findByText('Lượt quay đã hết hạn.')).toBeTruthy();
  });
});

describe('counter check-in code', () => {
  it('shows the rotating code and a countdown to staff, and explains when codes are off', async () => {
    window.location.hash = '#/checkin-code';
    mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/checkin-code', () => json({ mode: 'code', enabled: true, code: 'K7M2PQ', expires_in_seconds: 125, rotation_seconds: 300 })],
      ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [] })], ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })]]);
    render(<App />);
    expect((await screen.findByTestId('checkin-code')).textContent).toBe('K7M2PQ');
    expect(screen.getByText(/0[12]:\d\d/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Gamification' })).toBeNull(); // nhân viên không cấu hình gamification
    cleanup();
    mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/checkin-code', () => json({ mode: 'wifi', enabled: false, code: 'K7M2PQ', expires_in_seconds: 125, rotation_seconds: 300 })]]);
    render(<App />);
    expect(await screen.findByText(/không cần mã/)).toBeTruthy();
    expect(screen.queryByTestId('checkin-code')).toBeNull();
  });
});

describe('owner gamification page', () => {
  const settings = { checkin_mode: 'wifi', checkin_points: 10, streak_milestones: [{ days: 3, bonus: 20 }], wheel_enabled: true, min_daily_prizes: 1, max_daily_prizes: 2,
    expected_daily_checkins: 20, spin_expiry_days: 1, code_rotation_seconds: 300 };
  const ownerPrizes = [
    { id: 1, name: '+20 điểm', kind: 'points', value: 20, percent: 40, weight_bp: 4000, stock: null, voucher_valid_days: 30 },
    { id: 3, name: 'Chúc may mắn', kind: 'nothing', value: 0, percent: 60, weight_bp: 6000, stock: null, voucher_valid_days: 30 },
  ];
  const base: Route[] = [['GET /api/auth/me', () => json(owner)], ['GET /api/venues/1/game-settings', () => json(settings)],
    ['GET /api/venues/1/networks', () => json({ networks: [{ cidr: '203.0.113.0/24', label: 'Wifi quán' }], your_ip: '198.51.100.4' })],
    ['GET /api/venues/1/wheel', () => json({ prizes: ownerPrizes, total_bp: 10000 })]];
  beforeEach(() => { window.location.hash = '#/game'; });

  it('saves settings and networks, and can add the owner current IP', async () => {
    const calls = mock([...base, ['PUT /api/venues/1/game-settings', () => json(settings)], ['PUT /api/venues/1/networks', () => json({ networks: [] })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Thêm IP này' }));
    fireEvent.click(screen.getByRole('button', { name: 'Lưu mạng' }));
    await waitFor(() => expect(bodyOf(calls, 'PUT /api/venues/1/networks').networks).toEqual([{ cidr: '203.0.113.0/24', label: 'Wifi quán' }, { cidr: '198.51.100.4', label: 'Mạng hiện tại' }]));
    fireEvent.change(screen.getByLabelText('Chế độ'), { target: { value: 'wifi_and_code' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cài đặt' }));
    await waitFor(() => expect(bodyOf(calls, 'PUT /api/venues/1/game-settings').checkin_mode).toBe('wifi_and_code'));
  });

  it('blocks saving the wheel unless the odds add up to exactly 100%, then sends basis points', async () => {
    const calls = mock([...base, ['PUT /api/venues/1/wheel', () => json({ prizes: ownerPrizes, total_bp: 10000 })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Vòng quay' }));
    expect((await screen.findByText('Tổng 100%'))).toBeTruthy();
    const percents = await screen.findAllByLabelText('Tỷ lệ (%)');
    fireEvent.change(percents[0], { target: { value: '45.5' } });
    expect(screen.getByText('Tổng 105.5%')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu vòng quay' }));
    expect(await screen.findByText('Tổng tỷ lệ phải đúng 100% (hiện 105.5%).')).toBeTruthy();
    expect(calls.some(c => c.key.startsWith('PUT /api/venues/1/wheel'))).toBe(false);
    fireEvent.change(percents[1], { target: { value: '54.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu vòng quay' }));
    await waitFor(() => expect(bodyOf(calls, 'PUT /api/venues/1/wheel').prizes.map((p: { weight_bp: number }) => p.weight_bp)).toEqual([4550, 5450]));
    expect(bodyOf(calls, 'PUT /api/venues/1/wheel').prizes[0].id).toBe(1); // giữ id ô cũ để giữ tồn kho
  });

  it('the sample wheel adds up to 100%', async () => {
    const calls = mock([...base, ['PUT /api/venues/1/wheel', () => json({ prizes: ownerPrizes, total_bp: 10000 })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Vòng quay' }));
    expect((await screen.findAllByLabelText('Tên ô')).length).toBe(2); // đợi dữ liệu từ máy chủ về trước
    fireEvent.click(screen.getByRole('button', { name: 'Điền cấu hình mẫu' }));
    await waitFor(() => expect(screen.getAllByLabelText('Tên ô').length).toBe(5));
    expect(screen.getByText('Tổng 100%')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu vòng quay' }));
    await waitFor(() => expect(bodyOf(calls, 'PUT /api/venues/1/wheel').prizes.length).toBe(5));
    expect(bodyOf(calls, 'PUT /api/venues/1/wheel').prizes.reduce((n: number, p: { weight_bp: number }) => n + p.weight_bp, 0)).toBe(10000);
  });

  it('shows today stats and warns when the guarantee is not met', async () => {
    const stats = { day: '2026-11-22', checkins_today: 7, plan: { expected: 5, min_prizes: 2, max_prizes: 3, spins: 6, prizes_given: 1, guaranteed_total: 2, guaranteed_given: 1, created: true },
      recent: [{ at: '2026-11-22T03:00:00Z', customer: 'Khách 1111', prize: '+20 điểm', kind: 'points' }] };
    mock([...base, ['GET /api/venues/1/game-stats', () => json(stats)]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Hôm nay' }));
    expect((await screen.findByTestId('guarantee')).textContent).toContain('1 / 2');
    expect(screen.getByText(/Chưa phát đủ thưởng đảm bảo/)).toBeTruthy();
    expect(screen.getByText('Khách 1111')).toBeTruthy();
  });

  it('is not reachable for staff', async () => {
    mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [] })],
      ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })]]);
    render(<App />);
    expect(await screen.findByText('Tổng quan bàn')).toBeTruthy();
    expect(screen.queryByText('Gamification')).toBeNull();
  });
});

describe('voucher at checkout', () => {
  it('lets staff pick the customer voucher, shows the server discount and sends the voucher id', async () => {
    const session = { id: 'sess-1', table_id: 2, table_name: 'Bàn 2', status: 'ACTIVE', started_at: 't', ended_at: null, rate_snapshot: 60000, customer_id: 9, void_reason: null,
      elapsed_seconds: 3600, billable_minutes: 60, table_amount: 60000, items_amount: 0, amount_vnd: 60000, deposit_applied: 0, voucher_discount: 0, amount_due: 60000, items: [],
      available_vouchers: [{ id: 5, code: 'ABCD2345', label: 'Giảm 10.000₫', kind: 'discount_vnd', value: 10000, expires_at: 't' }] };
    const table = { id: 2, name: 'Bàn 2', table_type: 'pool', hourly_rate: 60000, status: 'ACTIVE', session };
    const calls = mock([['GET /api/auth/me', () => json(staff)], ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [table] })],
      ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })],
      ['GET /api/venues/1/sessions/sess-1/quote?voucher_id=5', () => json({ ...session, voucher_discount: 10000, amount_vnd: 50000, amount_due: 50000 })],
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(session)],
      ['GET /api/venues/1/products', () => json([])], ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })],
      ['POST /api/venues/1/sessions/sess-1/checkout', () => json({ ...session, status: 'PAID', amount_vnd: 50000, amount_due: 50000 })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    fireEvent.change(within(dialog).getByLabelText('Voucher của khách'), { target: { value: '5' } });
    await waitFor(() => expect(within(dialog).getByTestId('voucher-discount').textContent).toContain('10.000'));
    expect(within(dialog).getByTestId('quote-amount').textContent).toContain('50.000');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đã thu tiền' }));
    await waitFor(() => expect(bodyOf(calls, 'POST /api/venues/1/sessions/sess-1/checkout')).toEqual({ payment_method: 'cash', voucher_id: 5 }));
  });
});
