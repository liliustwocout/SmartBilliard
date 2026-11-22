import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import type { PaymentMethod, Revenue, SessionView, TableRow, TablesResponse } from '../../api';
import { useAuth } from '../../auth';
import { duration, money } from '../../format';
import { useLoad } from '../../useLoad';
import { useNow } from '../../useNow';
import { Button, Card, EmptyState, ErrorState, Field, Modal, Skeleton, TableCard, useToast } from '../../ui/components';

const POLL_MS = 5000;

function CheckoutDialog({ venueId, table, isOwner, onClose, onDone }:
  { venueId: number; table: TableRow | null; isOwner: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [quote, setQuote] = useState<SessionView | null>(null);
  const [error, setError] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [mode, setMode] = useState<'pay' | 'void'>('pay');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const sessionId = table?.session?.id;

  useEffect(() => {
    setQuote(null); setError(''); setMode('pay'); setReason(''); setMethod('cash');
    if (!sessionId) return;
    let cancelled = false;
    api<SessionView>(`/venues/${venueId}/sessions/${sessionId}/quote`)
      .then(result => { if (!cancelled) setQuote(result); })
      .catch(reason => { if (!cancelled) setError((reason as Error).message); });
    return () => { cancelled = true; };
  }, [venueId, sessionId]);

  async function confirm() {
    if (!sessionId) return;
    setBusy(true); setError('');
    try {
      if (mode === 'pay') {
        const result = await api<SessionView>(`/venues/${venueId}/sessions/${sessionId}/checkout`, { body: { payment_method: method } });
        toast('success', `Đã thu ${money(result.amount_vnd)} · ${table?.name}.`);
      } else {
        await api(`/venues/${venueId}/sessions/${sessionId}/void`, { body: { reason } });
        toast('success', `Đã huỷ phiên ${table?.name}.`);
      }
      onDone();
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={table !== null} title={mode === 'pay' ? `Tính tiền ${table?.name ?? ''}` : `Huỷ phiên ${table?.name ?? ''}`} onClose={onClose}
      actions={<>
        {isOwner && mode === 'pay' && <Button variant="ghost" onClick={() => setMode('void')}>Huỷ phiên…</Button>}
        {mode === 'void' && <Button variant="ghost" onClick={() => setMode('pay')}>Quay lại</Button>}
        <Button onClick={onClose}>Đóng</Button>
        <Button variant={mode === 'pay' ? 'primary' : 'danger'} loading={busy} disabled={!quote || (mode === 'void' && reason.trim().length < 3)} onClick={() => void confirm()}>
          {mode === 'pay' ? 'Xác nhận đã thu tiền' : 'Huỷ phiên'}
        </Button>
      </>}>
      {!quote && !error && <Skeleton height={72} />}
      {quote && mode === 'pay' && (
        <>
          <dl className="credentials">
            <dt>Đã chơi</dt><dd className="num">{duration(quote.elapsed_seconds)}</dd>
            <dt>Tính theo</dt><dd className="num">{quote.billable_minutes} phút × {money(quote.rate_snapshot)}/giờ</dd>
            <dt>Cần thu</dt><dd className="num" data-testid="quote-amount" style={{ fontSize: 'var(--text-2xl)' }}>{money(quote.amount_vnd)}</dd>
          </dl>
          <p className="muted">Số tiền chốt tại thời điểm bạn xác nhận (có thể tăng thêm vài giây).</p>
          <fieldset className="method">
            <legend>Hình thức thanh toán</legend>
            {([['cash', 'Tiền mặt'], ['transfer', 'Chuyển khoản']] as const).map(([value, label]) => (
              <label key={value}><input type="radio" name="method" checked={method === value} onChange={() => setMethod(value)} /> {label}</label>
            ))}
          </fieldset>
        </>
      )}
      {mode === 'void' && (
        <>
          <p className="muted">Phiên bị huỷ sẽ không tính tiền và không hoàn tác được. Chỉ dùng khi mở nhầm bàn.</p>
          <Field label="Lý do huỷ" value={reason} onChange={e => setReason(e.target.value)} placeholder="Ví dụ: mở nhầm bàn" />
        </>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
    </Modal>
  );
}

export function ShopDashboardPage() {
  const { state } = useAuth();
  const toast = useToast();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const isOwner = user?.role === 'owner';
  const tables = useLoad(() => api<TablesResponse>(`/venues/${venueId}/tables`), [venueId]);
  const revenue = useLoad(() => api<Revenue>(`/venues/${venueId}/revenue/today`), [venueId]);
  const [checkout, setCheckout] = useState<TableRow | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const now = useNow(1000);
  const fetchedAt = useMemo(() => Date.now(), [tables.data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) { tables.reload(); revenue.reload(); } }, POLL_MS);
    return () => clearInterval(timer);
  }, [tables.reload, revenue.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openTable(table: TableRow) {
    setOpening(table.id);
    try {
      await api(`/venues/${venueId}/tables/${table.id}/open`, { body: {} });
      toast('success', `Đã mở ${table.name}.`);
    } catch (failure) {
      toast('error', (failure as Error).message); // 409 = bàn vừa được mở ở nơi khác: tải lại để thấy phiên đó
    } finally { setOpening(null); tables.reload(); }
  }

  if (tables.error && !tables.data) return <Card><ErrorState message={tables.error} onRetry={tables.reload} /></Card>;
  const visible = (tables.data?.tables ?? []).filter(t => t.status === 'ACTIVE');

  return (
    <>
      <div className="page-head">
        <h1>Tổng quan bàn</h1>
        <Card flat className="revenue" >
          <span className="muted">Doanh thu hôm nay</span>
          <span className="num" data-testid="revenue-today" style={{ fontSize: 'var(--text-2xl)', color: 'var(--brand)' }}>{money(revenue.data?.total_vnd ?? 0)}</span>
          <span className="muted">{revenue.data?.session_count ?? 0} phiên đã thanh toán</span>
        </Card>
      </div>

      {!tables.data ? <div className="grid-cards"><Skeleton height={230} /><Skeleton height={230} /><Skeleton height={230} /></div>
        : visible.length === 0 ? (
          <Card><EmptyState title="Quán chưa có bàn nào"
            description={isOwner ? 'Thêm bàn và đặt giá giờ để bắt đầu mở bàn, tính giờ.' : 'Nhờ chủ quán thêm bàn trước khi mở phiên.'}
            action={isOwner ? <a className="btn btn-primary" href="#/tables">Thêm bàn</a> : undefined} /></Card>
        ) : (
          <div className="grid-cards">
            {visible.map(table => {
              const session = table.session;
              const elapsed = session ? session.elapsed_seconds + Math.max(0, (now - fetchedAt) / 1000) : 0;
              return (
                <TableCard key={table.id} name={table.name} state={session ? 'playing' : 'free'} rate={`${money(table.hourly_rate)}/giờ`}
                  clock={session ? duration(elapsed) : undefined} amount={session ? money(session.amount_vnd) : undefined}
                  actions={session
                    ? <Button variant="primary" size="sm" onClick={() => setCheckout(table)}>Tính tiền</Button>
                    : <Button variant="primary" size="sm" loading={opening === table.id} onClick={() => void openTable(table)}>Mở bàn</Button>} />
              );
            })}
          </div>
        )}
      <CheckoutDialog venueId={venueId} table={checkout} isOwner={isOwner} onClose={() => setCheckout(null)}
        onDone={() => { setCheckout(null); tables.reload(); revenue.reload(); }} />
    </>
  );
}
