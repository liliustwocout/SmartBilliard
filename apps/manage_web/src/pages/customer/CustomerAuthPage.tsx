import { useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { PublicVenue } from '../../api';
import { useAuth } from '../../auth';
import { useLoad } from '../../useLoad';
import { Button, ErrorState, Field, Skeleton, Tabs } from '../../ui/components';
import { BrandBall, FeltTable } from '../../ui/FeltTable';
import { ThemeToggle } from '../../ui/ThemeToggle';

/** Trang vào của khách ở một quán: địa chỉ #/c/<địa-chỉ-quán>. Mỗi quán có tài khoản khách riêng. */
export function CustomerAuthPage({ slug, offline }: { slug: string; offline?: string }) {
  const { login, register } = useAuth();
  const venue = useLoad(() => api<PublicVenue>(`/public/venues/${encodeURIComponent(slug)}`), [slug]);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!phone.trim() || !password || (mode === 'register' && !name.trim())) { setError(mode === 'register' ? 'Nhập đủ tên, số điện thoại và mật khẩu.' : 'Nhập số điện thoại và mật khẩu.'); return; }
    setBusy(true); setError('');
    try {
      if (mode === 'login') await login(phone, password, slug);
      else await register(slug, name, phone, password);
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="customer-auth">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div className="brand" style={{ color: 'var(--brand)' }}><BrandBall />SmartBilliard</div>
        <ThemeToggle />
      </div>
      {venue.error ? <ErrorState message={venue.error === 'Không tìm thấy quán.' ? 'Địa chỉ quán không đúng hoặc quán đang tạm ngưng.' : venue.error} onRetry={venue.reload} />
        : !venue.data ? <Skeleton height={120} />
        : (
          <>
            <div className="customer-hero">
              <FeltTable title="" />
              <div className="stack" style={{ gap: 4 }}>
                <p className="muted">Chào mừng đến</p>
                <h1>{venue.data.name}</h1>
              </div>
            </div>
            <Tabs label="Đăng nhập hoặc đăng ký" value={mode} onChange={id => { setMode(id); setError(''); }}
              tabs={[{ id: 'login', label: 'Đăng nhập' }, { id: 'register', label: 'Đăng ký' }]} />
            <form className="stack" onSubmit={submit} noValidate>
              {offline && <p className="notice" role="alert">{`Chưa kết nối được máy chủ: ${offline}`}</p>}
              {mode === 'register' && <Field label="Tên của bạn" autoComplete="name" value={name} onChange={e => setName(e.target.value)} />}
              <Field label="Số điện thoại" inputMode="tel" autoComplete="tel" value={phone} onChange={e => setPhone(e.target.value)} />
              <Field label="Mật khẩu" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password}
                onChange={e => setPassword(e.target.value)} hint={mode === 'register' ? 'Ít nhất 10 ký tự.' : undefined} />
              {error && <p className="field-error" role="alert">{error}</p>}
              <Button type="submit" variant="primary" size="lg" block loading={busy}>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}</Button>
            </form>
          </>
        )}
    </main>
  );
}
