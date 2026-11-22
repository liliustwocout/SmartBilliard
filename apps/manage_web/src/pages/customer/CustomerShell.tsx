import type { ReactNode } from 'react';
import { useAuth } from '../../auth';
import { Button } from '../../ui/components';
import { BrandBall } from '../../ui/FeltTable';
import { ThemeToggle } from '../../ui/ThemeToggle';

export type CustomerPage = 'book' | 'bookings' | 'history' | 'rewards';

const NAV: Array<{ page: CustomerPage; href: string; label: string }> = [
  { page: 'book', href: '#/', label: 'Đặt bàn' },
  { page: 'bookings', href: '#/my/bookings', label: 'Lịch đặt' },
  { page: 'rewards', href: '#/my/rewards', label: 'Quà tặng' },
  { page: 'history', href: '#/my/history', label: 'Lịch sử' },
];

/** Khung dành cho khách, ưu tiên điện thoại: thanh điều hướng cố định ở đáy màn hình. */
export function CustomerShell({ page, children }: { page: CustomerPage; children: ReactNode }) {
  const { state, logout } = useAuth();
  const user = state.status === 'ready' ? state.user : null;

  async function leave() {
    const slug = user?.venue?.slug;
    await logout();
    if (slug) window.location.hash = `#/c/${slug}`;
  }

  return (
    <div className="customer-shell">
      <header className="customer-top">
        <div className="brand"><BrandBall /><span>{user?.venue?.name ?? 'SmartBilliard'}</span></div>
        <div className="row">
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={() => void leave()}>Đăng xuất</Button>
        </div>
      </header>
      <main className="customer-main">
        <p className="muted">Xin chào, <strong>{user?.display_name}</strong></p>
        {children}
      </main>
      <nav className="customer-nav" aria-label="Điều hướng khách">
        {NAV.map(item => <a key={item.page} href={item.href} aria-current={item.page === page ? 'page' : undefined}>{item.label}</a>)}
      </nav>
    </div>
  );
}
