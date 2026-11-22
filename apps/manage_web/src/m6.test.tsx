// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser, RevenueReport } from './api';
import { BarChart, niceMax, shortMoney } from './ui/BarChart';
import { periodLabel, rangeFor } from './pages/shop/ReportsPage';
import { money } from './format';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-22T03:00:00Z'));
  window.location.hash = '#/reports';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const venue = { id: 1, name: 'Quán A', slug: 'quan-a' };
const owner: AuthUser = { id: 2, role: 'owner', login: 'o', display_name: 'Chủ A', must_change_password: false, venue, csrf_token: 'tok' };
const staff: AuthUser = { ...owner, id: 3, role: 'staff' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const report: RevenueReport = {
  from: '2026-10-24', to: '2026-11-22', group: 'day',
  totals: { revenue: 320000, sessions: 3, table_amount: 300000, items_amount: 20000, voucher_discount: 10000, deposit_applied: 50000, collected_cash: 200000, collected_transfer: 60000 },
  series: [{ key: '2026-11-21', revenue: 0, sessions: 0 }, { key: '2026-11-22', revenue: 320000, sessions: 3 }],
  by_table: [{ table_id: 1, table_name: 'Bàn 1', sessions: 2, minutes: 180, revenue: 200000 }, { table_id: 2, table_name: 'Bàn VIP', sessions: 1, minutes: 60, revenue: 120000 }],
  top_items: [{ name: 'Nước suối', quantity: 4, amount: 40000 }],
  sessions_by_start_hour: Array.from({ length: 24 }, (_, h) => (h === 10 ? 2 : h === 19 ? 1 : 0)),
};

function mock(handler: (url: string) => Response) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (url === '/api/auth/me') return json(owner);
    return handler(url);
  }));
  return calls;
}

describe('chart helpers', () => {
  it('formats axis money and picks nice maxima', () => {
    expect(shortMoney(1_500_000)).toContain('1,5');
    expect(shortMoney(45_000)).toBe('45k');
    expect(shortMoney(0)).toBe('0');
    expect(niceMax(0)).toBe(1);
    expect(niceMax(320_000)).toBe(500_000);
    expect(niceMax(95)).toBe(100);
    expect(niceMax(2_100)).toBe(2_500);
  });

  it('renders one accessible bar per non-zero value and shows a tooltip on hover/focus', () => {
    render(<BarChart ariaLabel="Thử" format={money} bars={[{ label: '21/11', value: 0 }, { label: '22/11', value: 320000, detail: '3 phiên' }]} />);
    const bars = screen.getAllByRole('img').filter(el => el.getAttribute('tabindex') === '0');
    expect(bars).toHaveLength(1); // cột 0 không vẽ
    expect(bars[0].getAttribute('aria-label')).toContain('22/11');
    expect(bars[0].getAttribute('aria-label')).toContain('3 phiên');
    expect(screen.queryByRole('status')).toBeNull();
    fireEvent.focus(bars[0]);
    expect(screen.getByRole('status').textContent).toContain('320.000');
    fireEvent.blur(bars[0]);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('computes date ranges and period labels in Vietnam time', () => {
    expect(rangeFor('today', '2026-11-22')).toEqual({ from: '2026-11-22', to: '2026-11-22' });
    expect(rangeFor('7d', '2026-11-22')).toEqual({ from: '2026-11-16', to: '2026-11-22' });
    expect(rangeFor('30d', '2026-11-22')).toEqual({ from: '2026-10-24', to: '2026-11-22' });
    expect(rangeFor('month', '2026-11-22')).toEqual({ from: '2026-11-01', to: '2026-11-22' });
    expect(periodLabel('2026-11-22', 'day')).toBe('22/11');
    expect(periodLabel('2026-11-16', 'week')).toBe('T 16/11');
    expect(periodLabel('2026-11', 'month')).toBe('11/2026');
  });
});

describe('reports page', () => {
  it('shows totals that match the server, the by-table breakdown and top items', async () => {
    const calls = mock(() => json(report));
    render(<App />);
    expect((await screen.findByTestId('total-revenue')).textContent).toBe(money(320000));
    expect(screen.getByTestId('total-sessions').textContent).toBe('3');
    expect(screen.getByText('Bàn VIP')).toBeTruthy();
    expect(screen.getByText('Nước suối')).toBeTruthy();
    expect(calls.some(u => u.includes('date_from=2026-10-24') && u.includes('date_to=2026-11-22') && u.includes('group=day'))).toBe(true);
    expect(screen.getByText(/trước khi trừ tiền cọc/)).toBeTruthy();
  });

  it('re-queries when a preset or the grouping changes and links the CSV export to the same range', async () => {
    const calls = mock(() => json(report));
    render(<App />);
    await screen.findByTestId('total-revenue');
    fireEvent.click(screen.getByRole('tab', { name: '7 ngày' }));
    await waitFor(() => expect(calls.some(u => u.includes('date_from=2026-11-16') && u.includes('date_to=2026-11-22'))).toBe(true));
    fireEvent.click(screen.getByRole('tab', { name: 'Theo tuần' }));
    await waitFor(() => expect(calls.some(u => u.includes('group=week'))).toBe(true));
    const link = screen.getByRole('link', { name: 'Xuất CSV hoá đơn' });
    expect(link.getAttribute('href')).toBe('/api/venues/1/reports/export.csv?date_from=2026-11-16&date_to=2026-11-22');
    expect(link.hasAttribute('download')).toBe(true);
  });

  it('offers a custom range with date inputs and a table view of the chart data', async () => {
    const calls = mock(() => json(report));
    render(<App />);
    await screen.findByTestId('total-revenue');
    fireEvent.click(screen.getByRole('tab', { name: 'Tuỳ chọn' }));
    fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-11-01' } });
    await waitFor(() => expect(calls.some(u => u.includes('date_from=2026-11-01'))).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: 'Xem dạng bảng' }));
    const table = screen.getAllByRole('table')[0];
    expect(within(table).getByText('22/11')).toBeTruthy();
    expect(within(table).getByText(money(320000))).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Xem biểu đồ' }));
    expect(screen.getAllByRole('img').length).toBeGreaterThan(0);
  });

  it('shows an empty state without revenue and an error state with retry', async () => {
    mock(() => json({ ...report, totals: { ...report.totals, sessions: 0, revenue: 0 } }));
    render(<App />);
    expect(await screen.findByText('Chưa có doanh thu trong khoảng này')).toBeTruthy();
    cleanup();
    mock(() => json({ detail: 'Chỉ xem tối đa 366 ngày mỗi lần.' }, 400));
    render(<App />);
    expect(await screen.findByText('Chỉ xem tối đa 366 ngày mỗi lần.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeTruthy();
  });

  it('is owner-only in the UI (backend enforces it too)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/auth/me') return json(staff);
      if (url.includes('/tables')) return json({ server_time: 't', tables: [] });
      return json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] });
    }));
    render(<App />);
    expect(await screen.findByText('Tổng quan bàn')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Báo cáo' })).toBeNull();
  });
});
