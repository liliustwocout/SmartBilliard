import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../auth';
import { Button, Field } from '../ui/components';
import { FeltTable, BrandBall } from '../ui/FeltTable';
import { ThemeToggle } from '../ui/ThemeToggle';

export function LoginPage({ offline }: { offline?: string }) {
  const { login } = useAuth();
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ account?: string; password?: string }>({});
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!account.trim()) next.account = 'Nhập email hoặc số điện thoại.';
    if (!password) next.password = 'Nhập mật khẩu.';
    setErrors(next);
    setFailure('');
    if (Object.keys(next).length) return;
    setBusy(true);
    try { await login(account, password); } catch (reason) { setFailure((reason as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <aside className="login-art">
        <div className="brand"><BrandBall />SmartBilliard</div>
        <div className="stack">
          <h1>Mỗi bàn một đồng hồ, mỗi giờ một con số đúng.</h1>
          <p>Quản lý bàn, khách và doanh thu của quán trong một nơi.</p>
        </div>
        <FeltTable rack title="Bàn bi-a với 15 bi đã xếp sẵn và bi cái" />
      </aside>
      <main className="login-form">
        <form className="login-card" onSubmit={submit} noValidate>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Đăng nhập</h2>
            <ThemeToggle />
          </div>
          {offline && <p className="notice" role="alert">{`Chưa kết nối được máy chủ: ${offline}`}</p>}
          <Field label="Email hoặc số điện thoại" autoComplete="username" value={account} error={errors.account}
            onChange={e => setAccount(e.target.value)} />
          <Field label="Mật khẩu" type="password" autoComplete="current-password" value={password} error={errors.password}
            onChange={e => setPassword(e.target.value)} hint="Quên mật khẩu? Liên hệ quản trị viên hoặc chủ quán." />
          {failure && <p className="field-error" role="alert">{failure}</p>}
          <Button type="submit" variant="primary" size="lg" block loading={busy}>Đăng nhập</Button>
        </form>
      </main>
    </div>
  );
}
