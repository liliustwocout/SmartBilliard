// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { setCsrfToken } from './api';
import type { AuthUser } from './api';
import { applyTheme, currentTheme } from './theme';
import { Badge, Button, DataTable, EmptyState, Field, TableCard } from './ui/components';

const owner: AuthUser = {
  id: 2, role: 'owner', login: 'owner-a', display_name: 'Chủ quán A', must_change_password: false,
  venue: { id: 1, name: 'Quán A', slug: 'quan-a' }, csrf_token: 'csrf-123',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const health = { status: 'ok', app: 'manage', time: 't' };

type Handler = (init?: RequestInit) => Response | Promise<Response>;
function mockApi(routes: Record<string, Handler>) {
  const calls: Array<{ key: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    calls.push({ key, init });
    const handler = routes[key];
    return handler ? handler(init) : json({ detail: 'not mocked' }, 404);
  }));
  return calls;
}

beforeEach(() => { window.location.hash = ''; setCsrfToken(''); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('authentication flow', () => {
  it('shows the login form when there is no session', async () => {
    mockApi({ 'GET /api/auth/me': () => json({ detail: 'Cần đăng nhập.' }, 401) });
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Đăng nhập' })).toBeTruthy();
  });

  it('shows a connection notice when the server cannot be reached', async () => {
    mockApi({ 'GET /api/auth/me': () => json({}, 503) });
    render(<App />);
    expect(await screen.findByText(/Chưa kết nối được máy chủ/)).toBeTruthy();
  });

  it('validates empty fields and shows the server message on a bad login', async () => {
    mockApi({
      'GET /api/auth/me': () => json({ detail: 'x' }, 401),
      'POST /api/auth/login': () => json({ detail: 'Sai tài khoản hoặc mật khẩu.' }, 401),
    });
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText('Nhập email hoặc số điện thoại.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Email hoặc số điện thoại'), { target: { value: 'a@b.c' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText('Sai tài khoản hoặc mật khẩu.')).toBeTruthy();
  });

  it('logs in, shows the shell, sends the CSRF token on writes, and logs out', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => json({ detail: 'x' }, 401),
      'POST /api/auth/login': () => json(owner),
      'GET /api/venues/1/tables': () => json({ server_time: 't', tables: [] }),
      'GET /api/venues/1/revenue/today': () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] }),
      'POST /api/auth/logout': () => json({ ok: true }),
    });
    render(<App />);
    await screen.findByRole('button', { name: 'Đăng nhập' });
    fireEvent.change(screen.getByLabelText('Email hoặc số điện thoại'), { target: { value: 'owner-a' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'secret-pass-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText('Chủ quán A')).toBeTruthy();
    expect(screen.getByText(/Chủ quán · Quán A/)).toBeTruthy();
    expect(await screen.findByText('Quán chưa có bàn nào')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất' }));
    expect(await screen.findByRole('button', { name: 'Đăng nhập' })).toBeTruthy();
    const logout = calls.find(c => c.key === 'POST /api/auth/logout');
    expect((logout?.init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-123');
  });

  it('forces a password change before anything else and checks the confirmation', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => json({ ...owner, must_change_password: true }),
      'POST /api/auth/change-password': () => json({ ok: true }),
    });
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Đổi mật khẩu' })).toBeTruthy();
    expect(screen.queryByText('Tổng quan bàn')).toBeNull();
    fireEvent.change(screen.getByLabelText('Mật khẩu hiện tại'), { target: { value: 'old-pass-123' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu mới'), { target: { value: 'Mat-khau-moi-2026' } });
    fireEvent.change(screen.getByLabelText('Nhập lại mật khẩu mới'), { target: { value: 'khac' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu mật khẩu mới' }));
    expect(await screen.findByText('Hai lần nhập mật khẩu mới chưa khớp.')).toBeTruthy();
    expect(calls.some(c => c.key === 'POST /api/auth/change-password')).toBe(false);
  });
});

describe('dashboard', () => {
  it('shows the empty state for an owner without tables and an error if the tables cannot load', async () => {
    mockApi({
      'GET /api/auth/me': () => json(owner),
      'GET /api/venues/1/tables': () => json({ server_time: 't', tables: [] }),
      'GET /api/venues/1/revenue/today': () => json({ date: 'd', total_vnd: 0, session_count: 0, by_table: [] }),
    });
    render(<App />);
    expect(await screen.findByText('Quán chưa có bàn nào')).toBeTruthy();
    cleanup();
    mockApi({
      'GET /api/auth/me': () => json(owner),
      'GET /api/venues/1/tables': () => json({ detail: 'Máy chủ bận.' }, 500),
      'GET /api/venues/1/revenue/today': () => json({ detail: 'x' }, 500),
    });
    render(<App />);
    expect(await screen.findByText('Máy chủ bận.')).toBeTruthy();
  });
});

describe('design page (development only)', () => {
  it('labels sample data as illustrative', async () => {
    window.location.hash = '#/design';
    mockApi({ 'GET /api/auth/me': () => json(owner) });
    render(<App />);
    await waitFor(() => expect(screen.getByText(/không phải số liệu thật/)).toBeTruthy());
  });
});

describe('ui kit', () => {
  it('Field links label, hint and error for assistive tech', () => {
    render(<Field label="Tên bàn" error="Bắt buộc" />);
    const input = screen.getByLabelText('Tên bàn');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByRole('alert').textContent).toBe('Bắt buộc');
    expect(input.getAttribute('aria-describedby')).toBe(screen.getByRole('alert').id);
  });

  it('loading Button is disabled and busy', () => {
    render(<Button loading>Lưu</Button>);
    const button = screen.getByRole('button');
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');
  });

  it('DataTable renders the empty state when there are no rows', () => {
    render(<DataTable rows={[]} rowKey={() => 'x'} columns={[]} empty={<EmptyState title="Trống" description="Không có gì" />} />);
    expect(screen.getByText('Trống')).toBeTruthy();
  });

  it('TableCard only shows the clock while playing', () => {
    const { rerender } = render(<TableCard name="Bàn 1" state="free" clock="00:10:00" rate="x" />);
    expect(screen.queryByLabelText('Thời gian đã chơi')).toBeNull();
    rerender(<TableCard name="Bàn 1" state="playing" clock="00:10:00" rate="x" />);
    expect(screen.getByLabelText('Thời gian đã chơi').textContent).toBe('00:10:00');
    expect(screen.getByText('Đang chơi')).toBeTruthy();
    cleanup(); render(<Badge tone="ok">ok</Badge>);
  });
});

describe('theme', () => {
  it('defaults to light and applies the chosen theme', () => {
    delete document.documentElement.dataset.theme;
    localStorage.clear();
    expect(currentTheme()).toBe('light');
    applyTheme('dark');
    expect(currentTheme()).toBe('dark');
    applyTheme('light');
    expect(currentTheme()).toBe('light');
  });
});
