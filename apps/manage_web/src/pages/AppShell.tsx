import type { ReactNode } from 'react';
import { useAuth } from '../auth';
import type { Role } from '../api';
import { Button } from '../ui/components';
import { BrandBall } from '../ui/FeltTable';
import { ThemeToggle } from '../ui/ThemeToggle';

export type Route =
  | { name: 'home' } | { name: 'venues' } | { name: 'venue'; id: number } | { name: 'audit' } | { name: 'tables' } | { name: 'history' } | { name: 'design' };

export function parseRoute(hash: string, dev = import.meta.env.DEV): Route {
  const path = hash.replace(/^#/, '');
  if (path === '/venues') return { name: 'venues' };
  const venue = /^\/venues\/(\d+)$/.exec(path);
  if (venue) return { name: 'venue', id: Number(venue[1]) };
  if (path === '/audit') return { name: 'audit' };
  if (path === '/tables') return { name: 'tables' };
  if (path === '/history') return { name: 'history' };
  if (dev && path === '/design') return { name: 'design' };
  return { name: 'home' };
}

interface NavItem { href: string; label: string; active: (route: Route) => boolean; roles?: Role[]; devOnly?: boolean }

const NAV: NavItem[] = [
  { href: '#/', label: 'Tổng quan', active: r => r.name === 'home' },
  { href: '#/venues', label: 'Quán', roles: ['platform_admin'], active: r => r.name === 'venues' || r.name === 'venue' },
  { href: '#/tables', label: 'Bàn và giá', roles: ['owner'], active: r => r.name === 'tables' },
  { href: '#/history', label: 'Lịch sử phiên', roles: ['owner', 'staff'], active: r => r.name === 'history' },
  { href: '#/audit', label: 'Nhật ký', roles: ['platform_admin'], active: r => r.name === 'audit' },
  { href: '#/design', label: 'Giao diện mẫu', devOnly: true, active: r => r.name === 'design' },
];

export const ROLE_LABEL: Record<Role, string> = {
  platform_admin: 'Quản trị hệ thống', owner: 'Chủ quán', staff: 'Nhân viên', customer: 'Khách',
};

export function AppShell({ route, children }: { route: Route; children: ReactNode }) {
  const { state, logout } = useAuth();
  const user = state.status === 'ready' ? state.user : null;
  const items = NAV.filter(item => (!item.devOnly || import.meta.env.DEV) && (!item.roles || (user && item.roles.includes(user.role))));
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><BrandBall />SmartBilliard</div>
        <nav className="nav" aria-label="Điều hướng chính">
          {items.map(item => (
            <a key={item.href} href={item.href} aria-current={item.active(route) ? 'page' : undefined}>{item.label}</a>
          ))}
        </nav>
        <div className="sidebar-foot">
          {user && (
            <div className="hide-sm">
              <strong style={{ color: '#fff' }}>{user.display_name}</strong>
              <div>{ROLE_LABEL[user.role]}{user.venue ? ` · ${user.venue.name}` : ''}</div>
            </div>
          )}
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={() => void logout()}>Đăng xuất</Button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
