// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import App from './App';
import { applyTheme, currentTheme } from './theme';
import { Badge, Button, DataTable, EmptyState, Field, TableCard } from './ui/components';

const ok = () => new Response(JSON.stringify({ status: 'ok', app: 'manage', time: 't' }));

beforeEach(() => { window.location.hash = ''; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('dashboard route', () => {
  it('shows ready badge and an empty state when the manage API answers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok()));
    render(<App />);
    expect(await screen.findByText('Máy chủ sẵn sàng')).toBeTruthy();
    expect(screen.getByText('Quán chưa có bàn nào')).toBeTruthy();
  });

  it('refuses a non-manage server', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ status: 'ok', app: 'demo', time: 't' }))));
    render(<App />);
    expect(await screen.findByText(/nhầm máy chủ/)).toBeTruthy();
  });

  it('shows an error badge when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('x', { status: 503 })));
    render(<App />);
    expect(await screen.findByText(/Mất kết nối/)).toBeTruthy();
  });
});

describe('login route', () => {
  it('validates required fields and never claims a login succeeded', async () => {
    window.location.hash = '#/login';
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText('Nhập email hoặc số điện thoại.')).toBeTruthy();
    expect(screen.getByText('Nhập mật khẩu.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Email hoặc số điện thoại'), { target: { value: 'a@b.c' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByText(/chưa hoạt động/)).toBeTruthy();
  });
});

describe('design page', () => {
  it('labels sample data as illustrative', () => {
    window.location.hash = '#/design';
    render(<App />);
    expect(screen.getByText(/không phải số liệu thật/)).toBeTruthy();
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
  it('applies and reads the theme', () => {
    applyTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(currentTheme()).toBe('dark');
    applyTheme('light');
    expect(currentTheme()).toBe('light');
  });
});
