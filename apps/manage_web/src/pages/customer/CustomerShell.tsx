import type { ReactNode } from 'react';
import { useAuth } from '../../auth';

export type CustomerPage = 'home' | 'book' | 'spin' | 'wallet' | 'profile';

const ICON: Record<CustomerPage, ReactNode> = {
  home: <path d="M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10M10 19.5v-5h4v5" />,
  book: <path d="M4 6.5h16V20H4zM4 10.5h16M8.5 3.5v5M15.5 3.5v5" />,
  spin: <><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5v17M3.5 12h17M6 6l12 12M18 6 6 18" /></>,
  wallet: <path d="M3.5 7.5h16a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1zM3.5 7.5l12-3.5v3.5M16 14h4.5" />,
  profile: <><circle cx="12" cy="8.5" r="3.8" /><path d="M4.5 20c.6-4 3.6-6 7.5-6s6.9 2 7.5 6" /></>,
};

const NAV: Array<{ page: CustomerPage; href: string; label: string }> = [
  { page: 'home', href: '#/', label: 'Trang chủ' },
  { page: 'book', href: '#/my/book', label: 'Đặt bàn' },
  { page: 'spin', href: '#/my/spin', label: 'Vòng quay' },
  { page: 'wallet', href: '#/my/wallet', label: 'Ví' },
  { page: 'profile', href: '#/my/profile', label: 'Cá nhân' },
];

export function initials(name: string | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  return ((parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : parts[0]?.slice(0, 2)) ?? '?').toUpperCase();
}

/** Khung dành cho khách, ưu tiên điện thoại: 5 mục ở đáy, "Vòng quay" nổi ở giữa. */
export function CustomerShell({ page, back, children }: { page: CustomerPage; back?: { href: string; label: string }; children: ReactNode }) {
  const { state } = useAuth();
  const user = state.status === 'ready' ? state.user : null;
  return (
    <div className="customer-shell">
      <header className="customer-top">
        <div className="cx-venue"><span className="cx-venue-ball" aria-hidden="true" />{user?.venue?.name ?? 'SmartBilliard'}</div>
        <a className="cx-avatar" href="#/my/profile" aria-label="Tài khoản của tôi">{initials(user?.display_name)}</a>
      </header>
      <main className="customer-main">
        {back && <a className="back-link" href={back.href}>‹ {back.label}</a>}
        {children}
      </main>
      <nav className="customer-nav" aria-label="Điều hướng khách">
        {NAV.map(item => (
          <a key={item.page} href={item.href} className={item.page === 'spin' ? 'cx-nav-spin' : undefined} aria-current={item.page === page ? 'page' : undefined}>
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[item.page]}</svg>
            <span>{item.label}</span>
          </a>
        ))}
      </nav>
    </div>
  );
}
