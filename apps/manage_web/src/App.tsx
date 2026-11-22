import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './auth';
import { AppShell } from './pages/AppShell';
import type { Route } from './pages/AppShell';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import { DashboardPage } from './pages/DashboardPage';
import { DesignPage } from './pages/DesignPage';
import { LoginPage } from './pages/LoginPage';
import { Skeleton, ToastProvider } from './ui/components';

function readRoute(): Route {
  // Trang giao diện mẫu chỉ có ở môi trường phát triển.
  return import.meta.env.DEV && window.location.hash === '#/design' ? '/design' : '/';
}

function Router() {
  const { state } = useAuth();
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  if (state.status === 'loading') {
    return <div className="main" role="status" aria-label="Đang tải"><Skeleton width={220} height={32} /><Skeleton height={160} /></div>;
  }
  if (state.status === 'anonymous') return <LoginPage offline={state.offline} />;
  if (state.user.must_change_password) return <ChangePasswordPage />;
  return <AppShell route={route}>{route === '/design' ? <DesignPage /> : <DashboardPage />}</AppShell>;
}

export default function App() {
  return <ToastProvider><AuthProvider><Router /></AuthProvider></ToastProvider>;
}
