import { useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { GameState } from '../../api';
import { useAuth } from '../../auth';
import { useLoad } from '../../useLoad';
import { Button, Card, Field, useToast } from '../../ui/components';
import { ThemeToggle } from '../../ui/ThemeToggle';
import { initials } from './CustomerShell';

export function ProfilePage() {
  const { state, logout, changePassword } = useAuth();
  const toast = useToast();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const game = useLoad(() => api<GameState>(`/venues/${venueId}/my/game`), [venueId]);
  const [changing, setChanging] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function leave() {
    const slug = user?.venue?.slug;
    await logout();
    if (slug) window.location.hash = `#/c/${slug}`;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) { setError('Hai lần nhập mật khẩu mới chưa khớp.'); return; }
    setBusy(true); setError('');
    try {
      await changePassword(current, next);
      toast('success', 'Đã đổi mật khẩu.');
      setChanging(false); setCurrent(''); setNext(''); setConfirm('');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      <section className="profile-head">
        <span className="profile-avatar" aria-hidden="true">{initials(user?.display_name)}</span>
        <div><h1>{user?.display_name}</h1><p className="muted num">{user?.login}</p><p className="muted">{user?.venue?.name}</p></div>
      </section>

      {game.data && (
        <div className="profile-stats">
          <div><strong className="num">{game.data.points}</strong><span>điểm</span></div>
          <div><strong className="num">{game.data.streak}</strong><span>ngày liên tiếp</span></div>
          <div><strong>{game.data.level.name}</strong><span>hạng</span></div>
        </div>
      )}

      <nav className="menu-list" aria-label="Tài khoản">
        <a href="#/my/bookings"><span>Lịch đặt bàn</span><span aria-hidden="true">›</span></a>
        <a href="#/my/history"><span>Lịch sử chơi</span><span aria-hidden="true">›</span></a>
        <a href="#/my/wallet"><span>Ví và voucher</span><span aria-hidden="true">›</span></a>
      </nav>

      <Card>
        <div className="stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Mật khẩu</h2>
            {!changing && <Button size="sm" onClick={() => setChanging(true)}>Đổi mật khẩu</Button>}
          </div>
          {changing && (
            <form className="stack" onSubmit={submit} noValidate>
              <Field label="Mật khẩu hiện tại" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} />
              <Field label="Mật khẩu mới" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} hint="Ít nhất 10 ký tự, không toàn số." />
              <Field label="Nhập lại mật khẩu mới" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} error={error || undefined} />
              <div className="row"><Button variant="ghost" onClick={() => { setChanging(false); setError(''); }}>Huỷ</Button><Button type="submit" variant="primary" loading={busy}>Lưu mật khẩu mới</Button></div>
            </form>
          )}
        </div>
      </Card>

      <Card><div className="row" style={{ justifyContent: 'space-between' }}><span>Giao diện sáng/tối</span><ThemeToggle /></div></Card>
      <Button variant="danger" size="lg" block onClick={() => void leave()}>Đăng xuất</Button>
    </>
  );
}
