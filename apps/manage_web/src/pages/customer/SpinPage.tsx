import { useState } from 'react';
import { api } from '../../api';
import type { GameState, SpinResultView } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Button, Card, EmptyState, ErrorState, Modal, Skeleton } from '../../ui/components';
import { Wheel } from '../../ui/Wheel';
import { prizeText } from './prize';

/** Vòng quay may mắn. Không hiển thị tỷ lệ trúng: khách chỉ thấy các phần thưởng và kết quả máy chủ trả về. */
export function SpinPage() {
  const { state } = useAuth();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const game = useLoad(() => api<GameState>(`/venues/${venueId}/my/game`), [venueId]);
  const [spinning, setSpinning] = useState<{ ticketId: number; result: SpinResultView | null } | null>(null);
  const [revealed, setRevealed] = useState<SpinResultView | null>(null);
  const [spinError, setSpinError] = useState('');

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
  if (!data) return <Skeleton height={380} />;
  const target = spinning?.result?.prize_index ?? null;

  return (
    <>
      <div className="page-title"><h1>Vòng quay may mắn</h1><span className="chip-count num">{data.tickets.length} lượt</span></div>
      {!data.wheel.enabled ? <Card><EmptyState title="Vòng quay đang tạm tắt" description="Vòng quay của quán đang tạm tắt." /></Card> : (
        <Card className="spin-stage">
          <Wheel prizes={data.wheel.prizes} targetIndex={target} spinning={spinning !== null} onDone={finishSpin} />
          {data.tickets.length > 0
            ? <Button variant="primary" size="lg" block disabled={spinning !== null} onClick={() => void startSpin(data.tickets[0].id)}>Quay ({data.tickets.length} lượt)</Button>
            : <p className="muted" style={{ textAlign: 'center' }}>Bạn chưa có lượt quay. Check-in mỗi ngày để nhận lượt. <a href="#/">Về trang chủ</a></p>}
          {spinError && <p className="field-error" role="alert">{spinError}</p>}
          <p className="muted" style={{ textAlign: 'center' }}>Phần thưởng chỉ dùng tại quán, không quy đổi thành tiền.</p>
        </Card>
      )}

      <Modal open={revealed !== null} title={revealed?.prize.kind === 'nothing' ? 'Lần này chưa may mắn' : 'Chúc mừng bạn!'} onClose={() => setRevealed(null)}
        actions={<><a className="btn btn-secondary" href="#/my/wallet" onClick={() => setRevealed(null)}>Xem ví</a><Button variant="primary" onClick={() => setRevealed(null)}>Đóng</Button></>}>
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
