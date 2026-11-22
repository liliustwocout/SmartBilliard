import { useEffect, useState } from 'react';
import { AppShell } from './pages/AppShell';
import type { Route } from './pages/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { DesignPage } from './pages/DesignPage';
import { LoginPage } from './pages/LoginPage';
import { ToastProvider } from './ui/components';

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#/, '');
  return hash === '/design' || hash === '/login' ? hash : '/';
}

export default function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  return (
    <ToastProvider>
      {route === '/login' ? <LoginPage /> : (
        <AppShell route={route}>{route === '/design' ? <DesignPage /> : <DashboardPage />}</AppShell>
      )}
    </ToastProvider>
  );
}
