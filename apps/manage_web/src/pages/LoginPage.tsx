import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button, Field } from '../ui/components';
import { FeltTable, BrandBall } from '../ui/FeltTable';
import { ThemeToggle } from '../ui/ThemeToggle';

export function LoginPage() {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ account?: string; password?: string }>({});
  const [submitted, setSubmitted] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!account.trim()) next.account = 'Nhập email hoặc số điện thoại.';
    if (!password) next.password = 'Nhập mật khẩu.';
    setErrors(next);
    setSubmitted(Object.keys(next).length === 0);
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
          <Field label="Email hoặc số điện thoại" autoComplete="username" value={account} error={errors.account}
            onChange={e => setAccount(e.target.value)} />
          <Field label="Mật khẩu" type="password" autoComplete="current-password" value={password} error={errors.password}
            onChange={e => setPassword(e.target.value)} hint="Quên mật khẩu? Liên hệ quản trị viên hoặc chủ quán." />
          {submitted && <p className="notice" role="status">Đăng nhập chưa hoạt động: máy chủ chưa có tài khoản (đang phát triển).</p>}
          <Button type="submit" variant="primary" size="lg" block>Đăng nhập</Button>
        </form>
      </main>
    </div>
  );
}
