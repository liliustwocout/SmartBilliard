import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './auth';
import type { AuthUser } from './api';
import { AppShell, parseRoute } from './pages/AppShell';
import type { Route } from './pages/AppShell';
import { AdminAuditPage } from './pages/admin/AdminAuditPage';
import { AdminOverviewPage } from './pages/admin/AdminOverviewPage';
import { AdminVenueDetailPage } from './pages/admin/AdminVenueDetailPage';
import { AdminVenuesPage } from './pages/admin/AdminVenuesPage';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import { BookPage } from './pages/customer/BookPage';
import { CustomerAuthPage } from './pages/customer/CustomerAuthPage';
import { CustomerShell } from './pages/customer/CustomerShell';
import type { CustomerPage } from './pages/customer/CustomerShell';
import { MyBookingsPage } from './pages/customer/MyBookingsPage';
import { MyHistoryPage } from './pages/customer/MyHistoryPage';
import { HomePage } from './pages/customer/HomePage';
import { ProfilePage } from './pages/customer/ProfilePage';
import { SpinPage } from './pages/customer/SpinPage';
import { WalletPage } from './pages/customer/WalletPage';
import { CheckinCodePage } from './pages/shop/CheckinCodePage';
import { GamePage } from './pages/shop/GamePage';
import { ReportsPage } from './pages/shop/ReportsPage';
import { BookingsPage } from './pages/shop/BookingsPage';
import { CustomersPage } from './pages/shop/CustomersPage';
import { MenuPage } from './pages/shop/MenuPage';
import { StaffPage } from './pages/shop/StaffPage';
import { HistoryPage } from './pages/shop/HistoryPage';
import { ShopDashboardPage } from './pages/shop/ShopDashboardPage';
import { TablesManagePage } from './pages/shop/TablesManagePage';
import { DesignPage } from './pages/DesignPage';
import { LoginPage } from './pages/LoginPage';
import { Skeleton, ToastProvider } from './ui/components';

function Page({ route, user }: { route: Route; user: AuthUser }) {
  // Giao diện chỉ là lối vào; quyền thật do backend kiểm tra từng endpoint.
  if (route.name === 'design') return <DesignPage />;
  if (user.role === 'platform_admin') {
    if (route.name === 'venues') return <AdminVenuesPage />;
    if (route.name === 'venue') return <AdminVenueDetailPage key={route.id} venueId={route.id} />;
    if (route.name === 'audit') return <AdminAuditPage />;
    return <AdminOverviewPage />;
  }
  if (route.name === 'history') return <HistoryPage />;
  if (route.name === 'bookings') return <BookingsPage />;
  if (route.name === 'checkin-code') return <CheckinCodePage />;
  if (route.name === 'game' && user.role === 'owner') return <GamePage />;
  if (route.name === 'reports' && user.role === 'owner') return <ReportsPage />;
  if (route.name === 'customers') return <CustomersPage />;
  if (route.name === 'tables' && user.role === 'owner') return <TablesManagePage />;
  if (route.name === 'menu' && user.role === 'owner') return <MenuPage />;
  if (route.name === 'staff' && user.role === 'owner') return <StaffPage />;
  return <ShopDashboardPage />;
}

function customerPage(route: Route): CustomerPage {
  if (route.name === 'my-book') return 'book';
  if (route.name === 'my-spin') return 'spin';
  if (route.name === 'my-wallet') return 'wallet';
  if (route.name === 'my-profile' || route.name === 'my-bookings' || route.name === 'my-history') return 'profile';
  return 'home';
}

function Router() {
  const { state } = useAuth();
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  if (state.status === 'loading') {
    return <div className="main" role="status" aria-label="Đang tải"><Skeleton width={220} height={32} /><Skeleton height={160} /></div>;
  }
  if (state.status === 'anonymous') {
    return route.name === 'customer-entry' ? <CustomerAuthPage slug={route.slug} offline={state.offline} /> : <LoginPage offline={state.offline} />;
  }
  if (state.user.must_change_password) return <ChangePasswordPage />;
  if (state.user.role === 'customer') {
    const profileBack = { href: '#/my/profile', label: 'Cá nhân' };
    return (
      <CustomerShell page={customerPage(route)} back={route.name === 'my-bookings' || route.name === 'my-history' ? profileBack : undefined}>
        {route.name === 'my-bookings' ? <MyBookingsPage /> : route.name === 'my-history' ? <MyHistoryPage />
          : route.name === 'my-book' ? <BookPage /> : route.name === 'my-spin' ? <SpinPage /> : route.name === 'my-wallet' ? <WalletPage />
          : route.name === 'my-profile' ? <ProfilePage /> : <HomePage />}
      </CustomerShell>
    );
  }
  return <AppShell route={route}><Page route={route} user={state.user} /></AppShell>;
}

export default function App() {
  return <ToastProvider><AuthProvider><Router /></AuthProvider></ToastProvider>;
}
