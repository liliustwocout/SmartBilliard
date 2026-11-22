import { useState } from 'react';
import { api } from '../../api';
import type { CheckinResult, GameState, PrizeKind, SpinResultView } from '../../api';
import { useAuth } from '../../auth';
import { dateTime, money } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';
import { Wheel } from '../../ui/Wheel';

const REASON: Record<string, string> = { checkin: 'Check-in', streak_bonus: 'Thưởng chuỗi ngày', wheel: 'Vòng quay may mắn' };

export function prizeText(kind: PrizeKind, value: number, name: string): string {
  if (kind === 'points') return `+${value} điểm`;
  if (kind === 'discount_vnd') return `Giảm ${money(value)}`;
  if (kind === 'free_minutes') return `Miễn phí ${value} phút chơi`;
  return name;
}

export function RewardsPage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const game = useLoad(() => api<GameState>(`/venues/${venueId}/my/game`), [venueId]);
  const [code, setCode] = useState('');
  const [checkinError, setCheckinError] = useState('');
  const [busy, setBusy] = useState(false);
  const [spinning, setSpinning] = useState<{ ticketId: number; result: SpinResultView | null } | null>(null);
  const [revealed, setRevealed] = useState<SpinResultView | null>(null);
  const [spinError, setSpinError] = useState('');

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

  async function startSpin(ticketId: number) {
    setSpinError(''); setSpinning({ ticketId, result: null });
    try {
      const result = await api<SpinResultView>(`/venues/${venueId}/my/spins/${ticketId}/spin`, { method: 'POST', body: {} });
      setSpinning({ ticketId, result });
    } catch (failure) { setSpinning(null); setSpinError((failure as Error).message); game.reload(); }
  }

  function finishSpin() {
    if (spinning?.result) setRevealed(spinning.result);
    setSpinning(null);
    game.reload();
  }

  if (game.error && !game.data) return <Card><ErrorState message={game.error} onRetry={game.reload} /></Card>;
  const data = game.data;
  if (!data) return <Skeleton height={300} />;
  const target = spinning?.result?.prize_index ?? null;
  const pct = data.level.next_at ? Math.min(100, Math.round((data.points / data.level.next_at) * 100)) : 100;

  return (
    <>
      <h1>Quà tặng</h1>

      <Card className="reward-hero">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div><span className="muted">Điểm của bạn</span><div className="num stat" data-testid="points">{data.points}</div></div>
          <Badge tone="info">Hạng {data.level.name}</Badge>
        </div>
        <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
          aria-label={data.level.next_at ? `Tiến độ tới hạng tiếp theo (${data.level.next_at} điểm)` : 'Hạng cao nhất'}><span style={{ width: `${pct}%` }} /></div>
        <p className="muted">{data.level.next_at ? `Còn ${data.level.next_at - data.points} điểm để lên hạng tiếp theo.` : 'Bạn đang ở hạng cao nhất.'}</p>
      </Card>

      <Card>
        <div className="stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Check-in hằng ngày</h2>
            <span className="num" data-testid="streak" style={{ fontSize: 'var(--text-xl)' }}>🔥 {data.streak} ngày</span>
          </div>
          <div className="calendar" aria-label="14 ngày gần nhất">
            {data.calendar.map(day => <span key={day.day} className={`day${day.checked ? ' on' : ''}`} title={day.day} aria-label={`${day.day}: ${day.checked ? 'đã check-in' : 'chưa'}`} />)}
          </div>
          {data.next_milestone && <p className="muted">Check-in {data.next_milestone.days} ngày liên tiếp để nhận thêm +{data.next_milestone.bonus} điểm.</p>}
          {data.checkin_mode === 'off' ? <p className="notice">Quán chưa bật check-in.</p>
            : data.checked_in_today ? <p className="notice" role="status">Bạn đã check-in hôm nay. Hẹn gặp lại ngày mai!</p>
            : (
              <>
                {data.needs_code && <Field label="Mã check-in tại quầy" value={code} onChange={e => setCode(e.target.value.toUpperCase())} maxLength={8} autoComplete="off"
                  hint={data.checkin_mode === 'wifi_or_code' ? 'Không cần nhập nếu bạn đang dùng wifi của quán.' : undefined} />}
                {checkinError && <p className="field-error" role="alert">{checkinError}</p>}
                <Button variant="primary" size="lg" block loading={busy} onClick={() => void doCheckin()}>Check-in (+{data.checkin_points} điểm)</Button>
                {!data.needs_code && <p className="muted">Hãy kết nối wifi của quán trước khi check-in.</p>}
              </>
            )}
        </div>
      </Card>

      <Card>
        <div className="stack">
          <h2>Vòng quay may mắn</h2>
          {!data.wheel.enabled ? <p className="muted">Vòng quay của quán đang tạm tắt.</p> : (
            <>
              <Wheel prizes={data.wheel.prizes} targetIndex={target} spinning={spinning !== null} onDone={finishSpin} />
              {data.tickets.length > 0
                ? <Button variant="primary" size="lg" block disabled={spinning !== null} onClick={() => void startSpin(data.tickets[0].id)}>Quay ({data.tickets.length} lượt)</Button>
                : <p className="muted">Bạn chưa có lượt quay. Check-in mỗi ngày để nhận lượt.</p>}
              {spinError && <p className="field-error" role="alert">{spinError}</p>}
              <details className="odds">
                <summary>Xem tỷ lệ trúng</summary>
                <table className="data-table"><tbody>
                  {data.wheel.prizes.map(p => <tr key={p.id}><td>{prizeText(p.kind, p.value, p.name)}</td><td className="right num">{p.percent}%</td></tr>)}
                </tbody></table>
                {data.wheel.daily_guarantee && <p className="muted">Quán đảm bảo mỗi ngày có phần thưởng cho khách quay. Phần thưởng chỉ dùng tại quán, không quy đổi thành tiền.</p>}
              </details>
            </>
          )}
        </div>
      </Card>

      <Card>
        <div className="stack">
          <h2>Voucher của bạn</h2>
          {data.vouchers.length === 0 ? <p className="muted">Chưa có voucher. Trúng thưởng ở vòng quay để nhận.</p> : (
            <ul className="item-list">
              {data.vouchers.map(v => (
                <li key={v.id} style={{ gridTemplateColumns: '1fr auto' }}>
                  <span><strong>{v.label}</strong><br /><span className="muted">Hạn dùng {dateTime(v.expires_at)}</span></span>
                  <span className="num voucher-code" data-testid="voucher-code">{v.code}</span>
                </li>
              ))}
            </ul>
          )}
          {data.vouchers.length > 0 && <p className="muted">Đưa mã cho nhân viên khi tính tiền. Mỗi voucher dùng một lần.</p>}
        </div>
      </Card>

      {data.ledger.length > 0 && (
        <Card><div className="stack"><h2>Lịch sử điểm</h2>
          <ul className="item-list">{data.ledger.map((e, i) => (
            <li key={i}><span>{REASON[e.reason] ?? e.reason}</span><span className="num">{e.delta > 0 ? '+' : ''}{e.delta}</span><span className="muted">{dateTime(e.at)}</span></li>))}</ul>
        </div></Card>
      )}

      <Modal open={revealed !== null} title={revealed?.prize.kind === 'nothing' ? 'Lần này chưa may mắn' : 'Chúc mừng bạn!'} onClose={() => setRevealed(null)}
        actions={<Button variant="primary" onClick={() => setRevealed(null)}>Đóng</Button>}>
        {revealed && (
          <div className="stack">
            <p className="num" data-testid="prize-result" style={{ fontSize: 'var(--text-2xl)' }}>{prizeText(revealed.prize.kind, revealed.prize.value, revealed.prize.name)}</p>
            {revealed.voucher && <p>Mã voucher: <strong className="num voucher-code">{revealed.voucher.code}</strong><br /><span className="muted">Dùng trước {dateTime(revealed.voucher.expires_at)}</span></p>}
            {revealed.prize.kind === 'points' && <p className="muted">Tổng điểm của bạn: {revealed.points}.</p>}
            {revealed.prize.kind === 'nothing' && <p className="muted">Check-in ngày mai để nhận thêm lượt quay.</p>}
          </div>
        )}
      </Modal>
    </>
  );
}
