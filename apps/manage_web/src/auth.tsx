import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, api, setCsrfToken } from './api';
import type { AuthUser } from './api';

type AuthState = { status: 'loading' } | { status: 'anonymous'; offline?: string } | { status: 'ready'; user: AuthUser };

interface AuthApi {
  state: AuthState;
  login: (login: string, password: string, venueSlug?: string) => Promise<void>;
  register: (venueSlug: string, displayName: string, phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

export function useAuth(): AuthApi {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth cần nằm trong AuthProvider');
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  const accept = useCallback((user: AuthUser) => { setCsrfToken(user.csrf_token); setState({ status: 'ready', user }); }, []);

  useEffect(() => {
    let cancelled = false;
    api<AuthUser>('/auth/me')
      .then(user => { if (!cancelled) accept(user); })
      .catch(reason => {
        if (cancelled) return;
        // 401 = chưa đăng nhập; lỗi khác = không tới được máy chủ.
        setState({ status: 'anonymous', offline: reason instanceof ApiError && reason.status === 401 ? undefined : (reason as Error).message });
      });
    return () => { cancelled = true; };
  }, [accept]);

  const value = useMemo<AuthApi>(() => ({
    state,
    login: async (login, password, venueSlug) => {
      accept(await api<AuthUser>('/auth/login', { body: { login, password, venue_slug: venueSlug || null } }));
    },
    register: async (venueSlug, displayName, phone, password) => {
      accept(await api<AuthUser>('/auth/register', { body: { venue_slug: venueSlug, display_name: displayName, phone, password } }));
    },
    logout: async () => {
      try { await api('/auth/logout', { method: 'POST', body: {} }); } finally { setCsrfToken(''); setState({ status: 'anonymous' }); }
    },
    changePassword: async (current, next) => {
      await api('/auth/change-password', { body: { current_password: current, new_password: next } });
      accept(await api<AuthUser>('/auth/me'));
    },
  }), [state, accept]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
