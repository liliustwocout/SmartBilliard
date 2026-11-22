import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../auth';
import { Button, Field } from '../ui/components';
import { BrandBall } from '../ui/FeltTable';

export function ChangePasswordPage() {
  const { changePassword, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) { setError('Hai lần nhập mật khẩu mới chưa khớp.'); return; }
    setBusy(true); setError('');
    try { await changePassword(current, next); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="login-form" style={{ minHeight: '100dvh' }}>
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="brand" style={{ color: 'var(--brand)' }}><BrandBall />SmartBilliard</div>
        <div className="stack">
          <h1>Đổi mật khẩu</h1>
          <p className="muted">Tài khoản của bạn đang dùng mật khẩu tạm. Đặt mật khẩu mới (ít nhất 10 ký tự) để tiếp tục.</p>
        </div>
        <Field label="Mật khẩu hiện tại" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} />
        <Field label="Mật khẩu mới" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} />
        <Field label="Nhập lại mật khẩu mới" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} error={error || undefined} />
        <Button type="submit" variant="primary" size="lg" block loading={busy}>Lưu mật khẩu mới</Button>
        <Button variant="ghost" onClick={() => void logout()}>Đăng xuất</Button>
      </form>
    </main>
  );
}
