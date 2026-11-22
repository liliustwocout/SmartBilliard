import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import type { CustomerRow, ItemLine, Page, PaymentMethod, ProductRow, Revenue, SessionView, TableRow, TablesResponse } from '../../api';
import { useAuth } from '../../auth';
import { duration, money } from '../../format';
import { useLoad } from '../../useLoad';
import { useNow } from '../../useNow';
import { Button, Card, EmptyState, ErrorState, Field, Modal, SelectField, Skeleton, TableCard, useToast } from '../../ui/components';
import { Combobox } from '../../ui/Combobox';
import { InvoiceDialog } from '../../ui/InvoiceDialog';

const POLL_MS = 5000;

function localHm(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function CheckoutDialog({ venueId, table, isOwner, onClose, onDone, onChanged }:
  { venueId: number; table: TableRow | null; isOwner: boolean; onClose: () => void; onDone: (paidSessionId: string | null) => void; onChanged: () => void }) {
  const toast = useToast();
  const [quote, setQuote] = useState<SessionView | null>(null);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [error, setError] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [mode, setMode] = useState<'pay' | 'void'>('pay');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [productId, setProductId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [voucherId, setVoucherId] = useState('');
  const [startTime, setStartTime] = useState('');
  const sessionId = table?.session?.id;
  const base = `/venues/${venueId}/sessions/${sessionId}`;

  const refresh = useCallback(async (voucher = voucherId) => {
    if (!sessionId) return;
    setQuote(await api<SessionView>(`/venues/${venueId}/sessions/${sessionId}/quote${voucher ? `?voucher_id=${voucher}` : ''}`));
  }, [venueId, sessionId, voucherId]);

  useEffect(() => {
    setQuote(null); setError(''); setMode('pay'); setReason(''); setMethod('cash'); setProductId(''); setQuantity('1'); setVoucherId('');
    if (!sessionId) return;
    let cancelled = false;
    Promise.all([
      api<SessionView>(`/venues/${venueId}/sessions/${sessionId}/quote`),
      api<ProductRow[]>(`/venues/${venueId}/products`),
      api<Page<CustomerRow>>(`/venues/${venueId}/customers?limit=200`),
    ]).then(([q, p, c]) => { if (!cancelled) { setQuote(q); setStartTime(localHm(q.started_at)); setProducts(p.filter(x => x.status === 'ACTIVE')); setCustomers(c.items.filter(x => x.status === 'ACTIVE')); } })
      .catch(reason => { if (!cancelled) setError((reason as Error).message); });
    return () => { cancelled = true; };
  }, [venueId, sessionId]);

  async function guarded(work: () => Promise<void>) {
    setBusy(true); setError('');
    try { await work(); } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  const addItem = () => guarded(async () => {
    const qty = Number(quantity);
    if (!productId) throw new Error('Chọn món cần thêm.');
    if (!Number.isInteger(qty) || qty < 1 || qty > 99) throw new Error('Số lượng từ 1 đến 99.');
    await api<{ items: ItemLine[] }>(`${base}/items`, { body: { product_id: Number(productId), quantity: qty } });
    setProductId(''); setQuantity('1');
    await refresh();
  });
  const removeItem = (item: ItemLine) => guarded(async () => { await api(`${base}/items/${item.id}`, { method: 'DELETE' }); await refresh(); });
  const setCustomer = (value: string) => guarded(async () => {
    await api(`${base}/customer`, { method: 'PATCH', body: { customer_id: value ? Number(value) : null } });
    setVoucherId('');
    await refresh('');
  });

  const saveStart = () => guarded(async () => {
    const match = /^(\d{2}):(\d{2})$/.exec(startTime);
    if (!match) throw new Error('Nhập giờ bắt đầu dạng giờ:phút.');
    const when = new Date();
    when.setHours(Number(match[1]), Number(match[2]), 0, 0);
    if (when.getTime() > Date.now()) when.setDate(when.getDate() - 1); // giờ lớn hơn hiện tại → hiểu là hôm qua
    await api(`${base}/start`, { method: 'PATCH', body: { started_at: when.toISOString() } });
    toast('success', `Đã chỉnh giờ bắt đầu ${table?.name ?? ''}.`);
    await refresh();
    onChanged();
  });

  const confirm = () => guarded(async () => {
    if (!sessionId) return;
    if (mode === 'pay') {
      const result = await api<SessionView>(`${base}/checkout`, { body: { payment_method: method, voucher_id: voucherId ? Number(voucherId) : null } });
      toast('success', `Đã thu ${money(result.amount_due)} · ${table?.name}.`);
      onDone(sessionId);
    } else {
      await api(`${base}/void`, { body: { reason } });
      toast('success', `Đã huỷ phiên ${table?.name}.`);
      onDone(null);
    }
  });

  return (
    <Modal open={table !== null} title={mode === 'pay' ? `Chi tiết ${table?.name ?? ''}` :`Huỷ phiên ${table?.name ?? ''}`} onClose={onClose}
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
          <div className="row" style={{ alignItems: 'flex-end' }}>
            {isOwner ? (
              <>
                <div style={{ width: 140 }}><Field label="Giờ bắt đầu" type="time" value={startTime} onChange={e => setStartTime(e.target.value)} /></div>
                <Button disabled={busy || !startTime || startTime === localHm(quote.started_at)} onClick={() => void saveStart()}>Lưu giờ</Button>
                <span className="muted">Dùng khi quên mở bàn đúng lúc (tối đa lùi 24 giờ).</span>
              </>
            ) : <span className="muted">Bắt đầu lúc <strong className="num">{localHm(quote.started_at)}</strong> · chỉ chủ quán chỉnh được giờ.</span>}
          </div>
          <dl className="credentials">
            <dt>Đã chơi</dt><dd className="num">{duration(quote.elapsed_seconds)}</dd>
            <dt>Tiền giờ</dt><dd className="num">{quote.billable_minutes} phút × {money(quote.rate_snapshot)}/giờ = {money(quote.table_amount)}</dd>
            <dt>Dịch vụ</dt><dd className="num" data-testid="items-amount">{money(quote.items_amount)}</dd>
            {quote.voucher_discount > 0 && <><dt>Voucher</dt><dd className="num" data-testid="voucher-discount">− {money(quote.voucher_discount)}</dd></>}
            <dt>Tổng hoá đơn</dt><dd className="num" data-testid="quote-total">{money(quote.amount_vnd)}</dd>
            {quote.deposit_applied > 0 && <><dt>Đã cọc (mô phỏng)</dt><dd className="num" data-testid="deposit-applied">− {money(quote.deposit_applied)}</dd></>}
            <dt>Cần thu</dt><dd className="num" data-testid="quote-amount" style={{ fontSize: 'var(--text-2xl)' }}>{money(quote.amount_due)}</dd>
          </dl>

          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            <strong>Dịch vụ đã gọi</strong>
            {(quote.items ?? []).length === 0 ? <p className="muted">Chưa gọi món nào.</p> : (
              <ul className="item-list">
                {(quote.items ?? []).map(item => (
                  <li key={item.id}>
                    <span>{item.name} × {item.quantity}</span>
                    <span className="num">{money(item.amount)}</span>
                    <Button size="sm" variant="ghost" aria-label={`Bỏ ${item.name}`} disabled={busy} onClick={() => void removeItem(item)}>✕</Button>
                  </li>
                ))}
              </ul>
            )}
            <div className="row" style={{ alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 160px' }}>
                <SelectField label="Thêm món" value={productId} onChange={e => setProductId(e.target.value)} disabled={products.length === 0}>
                  <option value="">{products.length === 0 ? 'Menu trống' : 'Chọn món…'}</option>
                  {products.map(p => <option key={p.id} value={p.id}>{p.name} — {money(p.price)}</option>)}
                </SelectField>
              </div>
              <div style={{ width: 84 }}><Field label="Số lượng" inputMode="numeric" value={quantity} onChange={e => setQuantity(e.target.value)} /></div>
              <Button disabled={busy || products.length === 0} onClick={() => void addItem()}>Thêm</Button>
            </div>
          </div>

          <Combobox label="Khách (không bắt buộc)" value={quote.customer_id ? String(quote.customer_id) : ''} onChange={value => void setCustomer(value)}
            emptyLabel="Khách vãng lai" placeholder="Gõ tên hoặc số điện thoại…" disabled={busy}
            options={customers.map(c => ({ value: String(c.id), label: c.display_name, hint: c.login }))} />

          {(quote.available_vouchers ?? []).length > 0 && (
            <SelectField label="Voucher của khách" value={voucherId} onChange={e => { setVoucherId(e.target.value); void guarded(() => refresh(e.target.value)); }}>
              <option value="">Không dùng voucher</option>
              {(quote.available_vouchers ?? []).map(v => <option key={v.id} value={v.id}>{v.label} · {v.code}</option>)}
            </SelectField>
          )}

          <fieldset className="method">
            <legend>Hình thức thanh toán</legend>
            {([['cash', 'Tiền mặt'], ['transfer', 'Chuyển khoản']] as const).map(([value, label]) => (
              <label key={value}><input type="radio" name="method" checked={method === value} onChange={() => setMethod(value)} /> {label}</label>
            ))}
          </fieldset>
          <p className="muted">Số tiền chốt tại thời điểm bạn xác nhận (tiền giờ có thể tăng thêm vài giây).</p>
        </>
      )}
      {mode === 'void' && (
        <>
          <p className="muted">Phiên bị huỷ sẽ không tính tiền (kể cả dịch vụ đã gọi) và không hoàn tác được. Chỉ dùng khi mở nhầm bàn.</p>
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
  const [invoiceFor, setInvoiceFor] = useState<string | null>(null);
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
        <Card flat className="revenue">
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
                  onOpen={session ? () => setCheckout(table) : undefined}
                  actions={session
                    ? <Button variant="primary" size="sm" onClick={() => setCheckout(table)}>Tính tiền</Button>
                    : <Button variant="primary" size="sm" loading={opening === table.id} onClick={() => void openTable(table)}>Mở bàn</Button>} />
              );
            })}
          </div>
        )}
      <CheckoutDialog venueId={venueId} table={checkout} isOwner={isOwner} onClose={() => setCheckout(null)} onChanged={tables.reload}
        onDone={paidId => { setCheckout(null); tables.reload(); revenue.reload(); if (paidId) setInvoiceFor(paidId); }} />
      <InvoiceDialog venueId={venueId} sessionId={invoiceFor} onClose={() => setInvoiceFor(null)} />
    </>
  );
}
