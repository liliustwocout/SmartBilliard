import { useState } from 'react';
import { api } from '../../api';
import type { GameState } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Card, EmptyState, ErrorState, Skeleton, Tabs } from '../../ui/components';
import { REASON } from './prize';

type Tab = 'vouchers' | 'points';

export function WalletPage() {
  const { state } = useAuth();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const game = useLoad(() => api<GameState>(`/venues/${venueId}/my/game`), [venueId]);
  const [tab, setTab] = useState<Tab>('vouchers');

  if (game.error && !game.data) return <Card><ErrorState message={game.error} onRetry={game.reload} /></Card>;
  const data = game.data;
  if (!data) return <Skeleton height={300} />;

  return (
    <>
      <h1>Ví của tôi</h1>
      <section className="wallet-hero">
        <div><span>Điểm hiện có</span><strong className="num">{data.points}</strong></div>
        <div><span>Voucher</span><strong className="num">{data.vouchers.length}</strong></div>
        <div><span>Hạng</span><strong>{data.level.name}</strong></div>
      </section>
      <Tabs label="Nội dung ví" value={tab} onChange={setTab} tabs={[{ id: 'vouchers', label: 'Voucher' }, { id: 'points', label: 'Lịch sử điểm' }]} />

      {tab === 'vouchers' ? (
        data.vouchers.length === 0
          ? <Card><EmptyState title="Chưa có voucher" description="Trúng thưởng ở vòng quay để nhận voucher." action={<a className="btn btn-primary" href="#/my/spin">Đến vòng quay</a>} /></Card>
          : (
            <div className="stack">
              {data.vouchers.map(v => (
                <article key={v.id} className="voucher-ticket">
                  <div className="voucher-main"><strong>{v.label}</strong><span className="muted">Hạn dùng {dateTime(v.expires_at)}</span></div>
                  <div className="voucher-stub"><span>Mã</span><span className="num voucher-code" data-testid="voucher-code">{v.code}</span></div>
                </article>
              ))}
              <p className="muted">Đưa mã cho nhân viên khi tính tiền. Mỗi voucher dùng một lần và chỉ dùng tại quán.</p>
            </div>
          )
      ) : (
        data.ledger.length === 0
          ? <Card><EmptyState title="Chưa có điểm nào" description="Check-in hằng ngày để tích điểm." action={<a className="btn btn-primary" href="#/">Về trang chủ</a>} /></Card>
          : (
            <Card><ul className="item-list">{data.ledger.map((e, i) => (
              <li key={i}><span>{REASON[e.reason] ?? e.reason}<br /><span className="muted">{dateTime(e.at)}</span></span>
                <span className="num" style={{ color: e.delta > 0 ? 'var(--ok)' : 'var(--danger)', fontSize: 'var(--text-lg)' }}>{e.delta > 0 ? '+' : ''}{e.delta}</span></li>))}</ul></Card>
          )
      )}
    </>
  );
}
