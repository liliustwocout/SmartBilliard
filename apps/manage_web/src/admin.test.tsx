// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser, CustomerRow, VenueSummary } from './api';
import { dateTime } from './format';
import { parseRoute } from './pages/AppShell';

// jsdom chưa có showModal/close cho <dialog>.
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  window.location.hash = '';
  setCsrfToken('');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const admin: AuthUser = { id: 1, role: 'platform_admin', login: 'admin', display_name: 'Quản trị', must_change_password: false, venue: null, csrf_token: 'tok' };
const owner: AuthUser = { ...admin, id: 2, role: 'owner', display_name: 'Chủ A', venue: { id: 1, name: 'Quán A', slug: 'quan-a' } };
const venue: VenueSummary = {
  id: 7, name: 'Bi-a Đại Nam', slug: 'bi-a-dai-nam', status: 'ACTIVE', created_at: '2026-11-22T03:00:00Z',
  counts: { owners: 1, staff: 2, customers: 1 },
  owner: { id: 9, login: 'chu-dai-nam', display_name: 'Chủ Đại Nam', status: 'ACTIVE', must_change_password: true },
};
const customer: CustomerRow = { id: 21, login: '0901111111', display_name: 'An', status: 'ACTIVE', created_at: '2026-11-22T04:00:00Z' };

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mock(routes: Array<[string, (init?: RequestInit) => Response]>) {
  const calls: Array<{ key: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    calls.push({ key, init });
    const hit = routes.find(([prefix]) => key.startsWith(prefix));
    return hit ? hit[1](init) : json({ detail: 'not mocked' }, 404);
  }));
  return calls;
}

describe('navigation by role', () => {
  it('shows admin links to administrators only', async () => {
    mock([['GET /api/auth/me', () => json(admin)], ['GET /api/admin/overview', () => json({ venues: { active: 2, suspended: 1 }, users: { owner: 3, staff: 4, customer: 5 } })]]);
    render(<App />);
    expect(await screen.findByRole('link', { name: 'Quán' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Nhật ký' })).toBeTruthy();
    expect(await screen.findByText('Quán đang hoạt động')).toBeTruthy();
    cleanup();
    mock([['GET /api/auth/me', () => json(owner)], ['GET /api/venues/1/tables', () => json({ server_time: 't', tables: [] })], ['GET /api/venues/1/revenue/today', () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] })]]);
    render(<App />);
    await screen.findByText('Chủ A');
    expect(screen.queryByRole('link', { name: 'Quán' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Nhật ký' })).toBeNull();
  });

  it('parses routes and hides the design page outside development', () => {
    expect(parseRoute('#/venues')).toEqual({ name: 'venues' });
    expect(parseRoute('#/venues/12')).toEqual({ name: 'venue', id: 12 });
    expect(parseRoute('#/venues/abc')).toEqual({ name: 'home' });
    expect(parseRoute('#/design', true)).toEqual({ name: 'design' });
    expect(parseRoute('#/design', false)).toEqual({ name: 'home' });
  });

  it('formats UTC timestamps in Vietnam time', () => {
    expect(dateTime('2026-11-22T03:00:00Z')).toContain('10:00');
    expect(dateTime(null)).toBe('—');
    expect(dateTime('rác')).toBe('—');
  });
});

describe('venue list and creation', () => {
  it('lists venues and shows the empty state when there are none', async () => {
    window.location.hash = '#/venues';
    mock([['GET /api/auth/me', () => json(admin)], ['GET /api/admin/venues', () => json({ total: 1, items: [venue] })]]);
    render(<App />);
    expect(await screen.findByText('Bi-a Đại Nam')).toBeTruthy();
    expect(screen.getByText('Chủ Đại Nam (chu-dai-nam)')).toBeTruthy();
    cleanup();
    mock([['GET /api/auth/me', () => json(admin)], ['GET /api/admin/venues', () => json({ total: 0, items: [] })]]);
    render(<App />);
    expect(await screen.findByText('Chưa có quán nào')).toBeTruthy();
  });

  it('creates a venue, shows the temporary password once, then hides it', async () => {
    window.location.hash = '#/venues';
    const calls = mock([
      ['GET /api/auth/me', () => json(admin)],
      ['GET /api/admin/venues', () => json({ total: 0, items: [] })],
      ['POST /api/admin/venues', () => json({ venue, owner_temp_password: 'TempPass-Abc234' }, 201)],
    ]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Tạo quán' }))[0]);
    const form = await screen.findByRole('dialog', { name: 'Tạo quán mới' });
    fireEvent.click(within(form).getByRole('button', { name: 'Tạo quán' }));
    expect(await within(form).findByText(/Nhập tên quán/)).toBeTruthy();
    fireEvent.change(within(form).getByLabelText('Tên quán'), { target: { value: 'Bi-a Đại Nam' } });
    fireEvent.change(within(form).getByLabelText('Tên chủ quán'), { target: { value: 'Chủ Đại Nam' } });
    fireEvent.change(within(form).getByLabelText('Tên đăng nhập của chủ quán'), { target: { value: 'chu-dai-nam' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Tạo quán' }));
    expect((await screen.findByTestId('temp-password')).textContent).toBe('TempPass-Abc234');
    const post = calls.find(c => c.key === 'POST /api/admin/venues');
    expect(JSON.parse(String(post?.init?.body)).owner.login).toBe('chu-dai-nam');
    expect((post?.init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok');
    fireEvent.click(screen.getByText('Đã lưu, đóng lại'));
    await waitFor(() => expect(screen.queryByTestId('temp-password')?.textContent ?? '').toBe(''));
  });

  it('shows the server error when creation is rejected', async () => {
    window.location.hash = '#/venues';
    mock([
      ['GET /api/auth/me', () => json(admin)],
      ['GET /api/admin/venues', () => json({ total: 0, items: [] })],
      ['POST /api/admin/venues', () => json({ detail: 'Địa chỉ quán đã được dùng.' }, 409)],
    ]);
    render(<App />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Tạo quán' }))[0]);
    const form = await screen.findByRole('dialog', { name: 'Tạo quán mới' });
    for (const [label, value] of [['Tên quán', 'X quán'], ['Tên chủ quán', 'Y'], ['Tên đăng nhập của chủ quán', 'y-login']]) {
      fireEvent.change(within(form).getByLabelText(label), { target: { value } });
    }
    fireEvent.click(within(form).getByRole('button', { name: 'Tạo quán' }));
    expect(await within(form).findByText('Địa chỉ quán đã được dùng.')).toBeTruthy();
  });
});

describe('venue detail actions', () => {
  function detailMocks(extra: Array<[string, (init?: RequestInit) => Response]> = []) {
    window.location.hash = '#/venues/7';
    return mock([
      ['GET /api/auth/me', () => json(admin)],
      ['GET /api/admin/venues/7/customers', () => json({ total: 1, items: [customer] })],
      ['GET /api/admin/venues/7', () => json(venue)],
      ...extra,
    ]);
  }

  it('suspends only after confirmation', async () => {
    const calls = detailMocks([['PATCH /api/admin/venues/7', () => json({ ...venue, status: 'SUSPENDED' })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tạm ngưng quán' }));
    expect(calls.some(c => c.key.startsWith('PATCH'))).toBe(false);
    const dialog = await screen.findByRole('dialog', { name: 'Tạm ngưng Bi-a Đại Nam?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Tạm ngưng quán' }));
    await waitFor(() => expect(calls.some(c => c.key === 'PATCH /api/admin/venues/7')).toBe(true));
    const patch = calls.find(c => c.key === 'PATCH /api/admin/venues/7');
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ status: 'SUSPENDED' });
  });

  it('locks a customer and shows only that venue customers', async () => {
    const calls = detailMocks([['PATCH /api/admin/users/21/status', () => json({ id: 21, status: 'DISABLED' })]]);
    render(<App />);
    expect(await screen.findByText('0901111111')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Khoá' }));
    await waitFor(() => expect(calls.some(c => c.key === 'PATCH /api/admin/users/21/status')).toBe(true));
    expect(JSON.parse(String(calls.find(c => c.key.startsWith('PATCH'))?.init?.body))).toEqual({ status: 'DISABLED' });
  });

  it('resets the owner password and displays the new temporary one', async () => {
    detailMocks([['POST /api/admin/venues/7/owner/reset-password', () => json({ owner_login: 'chu-dai-nam', owner_temp_password: 'NewTemp-Xyz789' })]]);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Đặt lại mật khẩu chủ quán' }));
    const dialog = await screen.findByRole('dialog', { name: 'Đặt lại mật khẩu chủ quán?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Đặt lại mật khẩu' }));
    expect((await screen.findByTestId('temp-password')).textContent).toBe('NewTemp-Xyz789');
  });

  it('shows an error state with retry when the venue cannot be loaded', async () => {
    window.location.hash = '#/venues/7';
    mock([['GET /api/auth/me', () => json(admin)], ['GET /api/admin/venues/7', () => json({ detail: 'Không tìm thấy quán.' }, 404)]]);
    render(<App />);
    expect(await screen.findByText('Không tìm thấy quán.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeTruthy();
  });
});

describe('audit page', () => {
  it('translates actions and shows who did them', async () => {
    window.location.hash = '#/audit';
    mock([['GET /api/auth/me', () => json(admin)], ['GET /api/admin/audit', () => json([
      { id: 1, at: '2026-11-22T03:00:00Z', actor_user_id: 1, actor_login: 'admin', venue_id: 7, action: 'venue_created', target: 'bi-a-dai-nam', detail: {} },
    ])]]);
    render(<App />);
    expect(await screen.findByText('Tạo quán')).toBeTruthy();
    expect(screen.getByText('bi-a-dai-nam')).toBeTruthy();
    expect(screen.getByText('admin')).toBeTruthy();
  });

  it('sends the chosen filters to the server and can clear them', async () => {
    window.location.hash = '#/audit';
    const calls = mock([['GET /api/auth/me', () => json(admin)],
      ['GET /api/admin/venues', () => json({ total: 1, items: [{ id: 7, name: 'Bi-a Đại Nam', slug: 'bi-a-dai-nam', status: 'ACTIVE', created_at: 't', counts: { owners: 1, staff: 0, customers: 0 }, owner: null }] })],
      ['GET /api/admin/audit', () => json([])]]);
    render(<App />);
    fireEvent.change(await screen.findByRole('combobox', { name: 'Hành động' }), { target: { value: 'thanh toan' } }); // gõ không dấu vẫn tìm ra
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Thanh toán phiên' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Quán' }), { target: { value: 'dai nam' } });
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Bi-a Đại Nam/ }));
    fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-11-01' } });
    await waitFor(() => expect(calls.some(c => c.key.includes('action=session_paid') && c.key.includes('venue_id=7') && c.key.includes('date_from=2026-11-01'))).toBe(true));
    expect(await screen.findByText('Không có hoạt động khớp')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: 'Xoá bộ lọc' })[0]);
    await waitFor(() => expect((screen.getByRole('combobox', { name: 'Hành động' }) as HTMLInputElement).value).toBe('Tất cả hành động'));
  });
});
