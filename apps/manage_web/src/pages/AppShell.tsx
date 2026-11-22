import type { ReactNode } from 'react';
import { useAuth } from '../auth';
import type { Role } from '../api';
import { Button } from '../ui/components';
import { BrandBall } from '../ui/FeltTable';
import { ThemeToggle } from '../ui/ThemeToggle';

export type Route = '/' | '/design';

const NAV: Array<{ path: Route; label: string; devOnly?: boolean }> = [
  { path: '/', label: 'Tổng quan bàn' },
  { path: '/design', label: 'Giao diện mẫu', devOnly: true },
];

export const ROLE_LABEL: Record<Role, string> = {
  platform_admin: 'Quản trị hệ thống', owner: 'Chủ quán', staff: 'Nhân viên', customer: 'Khách',
};

export function AppShell({ route, children }: { route: Route; children: ReactNode }) {
  const { state, logout } = useAuth();
  const user = state.status === 'ready' ? state.user : null;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><BrandBall />SmartBilliard</div>
        <nav className="nav" aria-label="Điều hướng chính">
          {NAV.filter(item => !item.devOnly || import.meta.env.DEV).map(item => (
            <a key={item.path} href={`#${item.path}`} aria-current={route === item.path ? 'page' : undefined}>{item.label}</a>
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
