import { useState } from 'react';
import { api } from '../../api';
import type { BookingView, CheckinResult, GameState } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { BOOKING_LABEL } from '../../labels';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ErrorState, Field, Skeleton, useToast } from '../../ui/components';

function greeting(): string {
  const hour = Number(new Date().toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: 'Asia/Ho_Chi_Minh' }));
  return hour < 11 ? 'Chào buổi sáng' : hour < 14 ? 'Chào buổi trưa' : hour < 18 ? 'Chào buổi chiều' : 'Chào buổi tối';
}

export function HomePage() {
  const { state } = useAuth();
  const toast = useToast();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const game = useLoad(() => api<GameState>(`/venues/${venueId}/my/game`), [venueId]);
  const bookings = useLoad(() => api<BookingView[]>(`/venues/${venueId}/my/bookings`), [venueId]);
  const [code, setCode] = useState('');
  const [checkinError, setCheckinError] = useState('');
  const [busy, setBusy] = useState(false);

  async function doCheckin() {
    setBusy(true); setCheckinError('');
    try {
      const result = await api<CheckinResult>(`/venues/${venueId}/my/checkin`, { body: { code: code.trim() || null } });
      if (result.already_checked_in) toast('info', 'Bạn đã check-in hôm nay rồi.');
      else toast('success', `Check-in thành công: +${result.points_added + (result.streak_bonus ?? 0)} điểm${result.ticket_id ? ' và 1 lượt quay' : ''}.`);
      setCode('');
      game.reload();
    } catch (failure) { setCheckinError((failure as Error).message); } finally { setBusy(false); }
  }

  if (game.error && !game.data) return <Card><ErrorState message={game.error} onRetry={game.reload} /></Card>;
  const data = game.data;
  if (!data) return <div className="stack"><Skeleton height={230} /><Skeleton height={120} /></div>;
  const pct = data.level.next_at ? Math.min(100, Math.round((data.points / data.level.next_at) * 100)) : 100;
  const upcoming = (bookings.data ?? []).filter(b => (b.status === 'PENDING' || b.status === 'CONFIRMED') && new Date(b.end_at).getTime() > Date.now())
    .sort((a, b) => a.start_at.localeCompare(b.start_at))[0];

  return (
    <>
      <section className="member-card" aria-label="Thẻ thành viên">
        <div className="member-top">
          <div>
            <p className="member-hello">{greeting()},</p>
            <h1 className="member-name">{user?.display_name}</h1>
          </div>
          <span className="member-level">Hạng {data.level.name}</span>
        </div>
        <div className="member-points"><span className="num" data-testid="points">{data.points}</span><span>điểm</span></div>
        <div className="progress on-cloth" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
          aria-label={data.level.next_at ? `Tiến độ tới hạng tiếp theo (${data.level.next_at} điểm)` : 'Hạng cao nhất'}><span style={{ width: `${pct}%` }} /></div>
        <p className="member-note">{data.level.next_at ? `Còn ${data.level.next_at - data.points} điểm để lên hạng tiếp theo.` : 'Bạn đang ở hạng cao nhất.'}</p>
        <div className="rack" aria-label="14 ngày gần nhất">
          {data.calendar.map(day => <span key={day.day} className={`ball${day.checked ? ' on' : ''}`} title={day.day} aria-label={`${day.day}: ${day.checked ? 'đã check-in' : 'chưa'}`} />)}
        </div>
        <p className="member-streak"><strong className="num" data-testid="streak">🔥 {data.streak} ngày</strong> liên tiếp{data.best_streak > data.streak ? ` · kỷ lục ${data.best_streak} ngày` : ''}</p>
      </section>

      {data.checkin_mode !== 'off' && (
        <Card>
          <div className="stack">
            {data.checked_in_today ? <p className="notice" role="status">Bạn đã check-in hôm nay. Hẹn gặp lại ngày mai!</p> : (
              <>
                <h2>Check-in hôm nay</h2>
                {data.next_milestone && <p className="muted">Check-in {data.next_milestone.days} ngày liên tiếp để nhận thêm +{data.next_milestone.bonus} điểm.</p>}
                {data.needs_code && <Field label="Mã check-in tại quầy" value={code} onChange={e => setCode(e.target.value.toUpperCase())} maxLength={8} autoComplete="off"
                  hint={data.checkin_mode === 'wifi_or_code' ? 'Không cần nhập nếu bạn đang dùng wifi của quán.' : undefined} />}
                {checkinError && <p className="field-error" role="alert">{checkinError}</p>}
                <Button variant="primary" size="lg" block loading={busy} onClick={() => void doCheckin()}>Check-in (+{data.checkin_points} điểm)</Button>
                {!data.needs_code && <p className="muted">Hãy kết nối wifi của quán trước khi check-in.</p>}
              </>
            )}
          </div>
        </Card>
      )}

      <div className="tiles">
        <a className="tile" href="#/my/spin"><span className="tile-count num">{data.tickets.length}</span><strong>Lượt quay</strong><span className="muted">{data.tickets.length > 0 ? 'Quay ngay' : 'Check-in để nhận'}</span></a>
        <a className="tile" href="#/my/wallet"><span className="tile-count num">{data.vouchers.length}</span><strong>Voucher</strong><span className="muted">Trong ví của bạn</span></a>
        <a className="tile" href="#/my/book"><span className="tile-count" aria-hidden="true">＋</span><strong>Đặt bàn</strong><span className="muted">Chọn bàn và giờ</span></a>
        <a className="tile" href="#/my/history"><span className="tile-count" aria-hidden="true">↺</span><strong>Lịch sử chơi</strong><span className="muted">Các lần đã chơi</span></a>
      </div>

      {upcoming && (
        <Card className="booking-card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Lịch đặt sắp tới</h2><Badge tone={BOOKING_LABEL[upcoming.status].tone}>{BOOKING_LABEL[upcoming.status].text}</Badge>
          </div>
          <p><strong>{upcoming.table_name}</strong> · {dateTime(upcoming.start_at)}</p>
          <a className="btn btn-secondary" href="#/my/bookings">Xem lịch đặt</a>
        </Card>
      )}
    </>
  );
}
