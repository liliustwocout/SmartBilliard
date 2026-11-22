// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser, Invoice, SessionView, TableRow } from './api';
import { money } from './format';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  window.location.hash = '';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const venue = { id: 1, name: 'Quán A', slug: 'quan-a' };
const owner: AuthUser = { id: 2, role: 'owner', login: 'o', display_name: 'Chủ A', must_change_password: false, venue, csrf_token: 'tok' };
const staff: AuthUser = { ...owner, id: 3, role: 'staff', login: 's', display_name: 'Thu ngân' };

const baseSession: SessionView = {
  id: 'sess-1', table_id: 2, table_name: 'Bàn 2', status: 'ACTIVE', started_at: '2026-11-22T03:00:00Z', ended_at: null,
  rate_snapshot: 60000, customer_id: null, void_reason: null, elapsed_seconds: 3600, billable_minutes: 60,
  table_amount: 60000, items_amount: 0, amount_vnd: 60000, items: [],
};
const playing: TableRow = { id: 2, name: 'Bàn 2', table_type: 'pool', hourly_rate: 60000, status: 'ACTIVE', session: baseSession };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

type Route = [string, (init?: RequestInit) => Response];
function mock(user: AuthUser, extra: Route[] = []) {
  const calls: Array<{ key: string; init?: RequestInit }> = [];
  const routes: Route[] = [
    ['GET /api/auth/me', () => json(user)],
    ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [playing] })],
    ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })],
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
const bodyOf = (calls: Array<{ key: string; init?: RequestInit }>, key: string) => JSON.parse(String(calls.find(c => c.key === key)?.init?.body ?? 'null'));

describe('items and customer inside checkout', () => {
  it('adds a menu item, shows the server total, and removes it again', async () => {
    let items: SessionView['items'] = [];
    const quote = () => json({ ...baseSession, items, items_amount: items!.reduce((n, i) => n + i.amount, 0), amount_vnd: 60000 + items!.reduce((n, i) => n + i.amount, 0) });
    const calls = mock(staff, [
      ['GET /api/venues/1/sessions/sess-1/quote', quote],
      ['GET /api/venues/1/products', () => json([{ id: 5, name: 'Nước suối', price: 10000, status: 'ACTIVE' }, { id: 6, name: 'Món cũ', price: 1, status: 'INACTIVE' }])],
      ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })],
      ['POST /api/venues/1/sessions/sess-1/items', () => { items = [{ id: 11, product_id: 5, name: 'Nước suối', unit_price: 10000, quantity: 2, amount: 20000 }]; return json({ items }, 201); }],
      ['DELETE /api/venues/1/sessions/sess-1/items/11', () => { items = []; return json({ items }); }],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    expect((await within(dialog).findByTestId('quote-amount')).textContent).toBe(money(60000));
    expect(within(dialog).queryByRole('option', { name: /Món cũ/ })).toBeNull(); // món ngừng bán không hiện
    fireEvent.change(within(dialog).getByLabelText('Thêm món'), { target: { value: '5' } });
    fireEvent.change(within(dialog).getByLabelText('Số lượng'), { target: { value: '2' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm' }));
    await waitFor(() => expect(within(dialog).getByTestId('quote-amount').textContent).toBe(money(80000)));
    expect(bodyOf(calls, 'POST /api/venues/1/sessions/sess-1/items')).toEqual({ product_id: 5, quantity: 2 });
    expect(within(dialog).getByText('Nước suối × 2')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Bỏ Nước suối' }));
    await waitFor(() => expect(within(dialog).getByTestId('quote-amount').textContent).toBe(money(60000)));
  });

  it('validates the item form before calling the server', async () => {
    const calls = mock(staff, [
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(baseSession)],
      ['GET /api/venues/1/products', () => json([{ id: 5, name: 'Nước suối', price: 10000, status: 'ACTIVE' }])],
      ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm' }));
    expect(await within(dialog).findByText('Chọn món cần thêm.')).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText('Thêm món'), { target: { value: '5' } });
    fireEvent.change(within(dialog).getByLabelText('Số lượng'), { target: { value: '100' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm' }));
    expect(await within(dialog).findByText('Số lượng từ 1 đến 99.')).toBeTruthy();
    expect(calls.some(c => c.key.startsWith('POST'))).toBe(false);
  });

  it('attaches a customer to the running session', async () => {
    const calls = mock(staff, [
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(baseSession)],
      ['GET /api/venues/1/products', () => json([])],
      ['GET /api/venues/1/customers', () => json({ total: 2, items: [
        { id: 31, login: '0901111111', display_name: 'An', status: 'ACTIVE', created_at: 't' },
        { id: 32, login: '0902222222', display_name: 'Bị khoá', status: 'DISABLED', created_at: 't' }] })],
      ['PATCH /api/venues/1/sessions/sess-1/customer', () => json({ customer_id: 31 })],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    expect(within(dialog).queryByRole('option', { name: /Bị khoá/ })).toBeNull();
    fireEvent.change(within(dialog).getByLabelText('Khách (không bắt buộc)'), { target: { value: '31' } });
    await waitFor(() => expect(bodyOf(calls, 'PATCH /api/venues/1/sessions/sess-1/customer')).toEqual({ customer_id: 31 }));
  });

  it('opens the invoice with the server total after paying', async () => {
    const invoice: Invoice = {
      venue_name: 'Quán A', invoice_no: 'ABCD1234', table_name: 'Bàn 2', started_at: '2026-11-22T03:00:00Z', ended_at: '2026-11-22T04:00:00Z',
      billable_minutes: 60, rate: 60000, table_amount: 60000, items: [{ id: 1, product_id: 5, name: 'Phấn', unit_price: 5000, quantity: 2, amount: 10000 }],
      items_amount: 10000, total: 70000, payment_method: 'cash', cashier: 'Thu ngân', customer: null,
    };
    mock(staff, [
      ['GET /api/venues/1/sessions/sess-1/quote', () => json(baseSession)],
      ['GET /api/venues/1/products', () => json([])],
      ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })],
      ['POST /api/venues/1/sessions/sess-1/checkout', () => json({ ...baseSession, status: 'PAID', amount_vnd: 70000 })],
      ['GET /api/venues/1/sessions/sess-1/invoice', () => json(invoice)],
    ]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tính tiền' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tính tiền Bàn 2' });
    await within(dialog).findByTestId('quote-amount');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đã thu tiền' }));
    expect((await screen.findByTestId('invoice-total')).textContent).toBe(money(70000));
    expect(screen.getByText('Phấn × 2')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'In hoá đơn' })).toBeTruthy();
  });
});

describe('staff management (owner)', () => {
  const row = { id: 7, login: 'nv-1', display_name: 'Lan', status: 'ACTIVE', must_change_password: true, created_at: '2026-11-22T03:00:00Z' };

  it('creates a staff member and shows the temporary password once', async () => {
    window.location.hash = '#/staff';
    const calls = mock(owner, [
      ['GET /api/venues/1/staff', () => json([])],
      ['POST /api/venues/1/staff', () => json({ staff: row, temp_password: 'TempNv-Abc234' }, 201)],
    ]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Thêm nhân viên' }))[0]);
    const form = await screen.findByRole('dialog', { name: 'Thêm nhân viên' });
    fireEvent.click(within(form).getByRole('button', { name: 'Thêm nhân viên' }));
    expect(await within(form).findByText('Nhập tên nhân viên và tên đăng nhập.')).toBeTruthy();
    fireEvent.change(within(form).getByLabelText('Tên nhân viên'), { target: { value: 'Lan' } });
    fireEvent.change(within(form).getByLabelText('Tên đăng nhập'), { target: { value: 'nv-1' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Thêm nhân viên' }));
    expect((await screen.findByTestId('temp-password')).textContent).toBe('TempNv-Abc234');
    expect(bodyOf(calls, 'POST /api/venues/1/staff')).toEqual({ login: 'nv-1', display_name: 'Lan' });
  });

  it('locks a staff member and lists the pending-password badge', async () => {
    window.location.hash = '#/staff';
    const calls = mock(owner, [
      ['GET /api/venues/1/staff', () => json([row])],
      ['PATCH /api/venues/1/staff/7', () => json({ ...row, status: 'DISABLED' })],
    ]);
    render(<App />);
    expect(await screen.findByText('Chưa đổi mật khẩu tạm')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Khoá' }));
    await waitFor(() => expect(bodyOf(calls, 'PATCH /api/venues/1/staff/7')).toEqual({ status: 'DISABLED' }));
  });

  it('staff cannot open the staff or menu pages and do not see their links', async () => {
    window.location.hash = '#/staff';
    mock(staff);
    render(<App />);
    expect(await screen.findByText('Tổng quan bàn')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Nhân viên' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Menu dịch vụ' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Khách hàng' })).toBeTruthy();
  });
});

describe('menu (owner)', () => {
  it('validates the price and posts a new product', async () => {
    window.location.hash = '#/menu';
    const calls = mock(owner, [
      ['GET /api/venues/1/products', () => json([])],
      ['POST /api/venues/1/products', () => json({ id: 9, name: 'Bia', price: 25000, status: 'ACTIVE' }, 201)],
    ]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Thêm món' }))[0]);
    const form = await screen.findByRole('dialog', { name: 'Thêm món' });
    fireEvent.change(within(form).getByLabelText('Tên món'), { target: { value: 'Bia' } });
    fireEvent.change(within(form).getByLabelText('Giá bán (₫)'), { target: { value: '-5' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Thêm món' }));
    expect(await within(form).findByText(/số nguyên từ 0 đến 10\.000\.000/)).toBeTruthy();
    fireEvent.change(within(form).getByLabelText('Giá bán (₫)'), { target: { value: '25000' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Thêm món' }));
    await waitFor(() => expect(bodyOf(calls, 'POST /api/venues/1/products')).toEqual({ name: 'Bia', price: 25000 }));
  });
});

describe('customers', () => {
  const customer = { id: 31, login: '0901111111', display_name: 'An', status: 'ACTIVE', created_at: '2026-11-22T03:00:00Z' };

  it('staff can add customers but not lock them; owner can', async () => {
    window.location.hash = '#/customers';
    mock(staff, [['GET /api/venues/1/customers', () => json({ total: 1, items: [customer] })]]);
    render(<App />);
    expect(await screen.findByText('0901111111')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Thêm khách' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Khoá' })).toBeNull();
    cleanup();
    mock(owner, [['GET /api/venues/1/customers', () => json({ total: 1, items: [customer] })]]);
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Khoá' })).toBeTruthy();
  });

  it('creates a customer by phone and shows the temporary password', async () => {
    window.location.hash = '#/customers';
    const calls = mock(staff, [
      ['GET /api/venues/1/customers', () => json({ total: 0, items: [] })],
      ['POST /api/venues/1/customers', () => json({ customer, temp_password: 'TempKh-Xyz789' }, 201)],
    ]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Thêm khách' }))[0]);
    const form = await screen.findByRole('dialog', { name: 'Thêm khách' });
    fireEvent.change(within(form).getByLabelText('Tên khách'), { target: { value: 'An' } });
    fireEvent.change(within(form).getByLabelText('Số điện thoại'), { target: { value: '0901 111 111' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Thêm khách' }));
    expect((await screen.findByTestId('temp-password')).textContent).toBe('TempKh-Xyz789');
    expect(bodyOf(calls, 'POST /api/venues/1/customers')).toEqual({ display_name: 'An', phone: '0901 111 111' });
  });
});
