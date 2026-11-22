import type { ReactNode } from 'react';
import { BrandBall } from '../ui/FeltTable';
import { ThemeToggle } from '../ui/ThemeToggle';

export type Route = '/' | '/design' | '/login';

const NAV: Array<{ path: Route; label: string }> = [
  { path: '/', label: 'Tổng quan bàn' },
  { path: '/design', label: 'Giao diện mẫu' },
];

export function AppShell({ route, children }: { route: Route; children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><BrandBall />SmartBilliard</div>
        <nav className="nav" aria-label="Điều hướng chính">
          {NAV.map(item => (
            <a key={item.path} href={`#${item.path}`} aria-current={route === item.path ? 'page' : undefined}>{item.label}</a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ThemeToggle />
          <a className="hide-sm" href="#/login" style={{ color: 'inherit' }}>Màn hình đăng nhập</a>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
