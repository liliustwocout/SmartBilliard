import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { BookingSettings, BookingView } from '../../api';
import { useAuth } from '../../auth';
import { dateTime, money } from '../../format';
import { BOOKING_LABEL, DEPOSIT_LABEL } from '../../labels';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, Skeleton, useToast } from '../../ui/components';

function SettingsCard({ venueId }: { venueId: number }) {
  const toast = useToast();
  const settings = useLoad(() => api<BookingSettings>(`/venues/${venueId}/booking-settings`), [venueId]);
  const [form, setForm] = useState({ deposit_amount: '', hold_minutes: '', refund_before_minutes: '', noshow_grace_minutes: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (settings.data) setForm({
      deposit_amount: String(settings.data.deposit_amount), hold_minutes: String(settings.data.hold_minutes),
      refund_before_minutes: String(settings.data.refund_before_minutes), noshow_grace_minutes: String(settings.data.noshow_grace_minutes),
    });
  }, [settings.data]);

  async function save(event: FormEvent) {
    event.preventDefault();
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v)]));
    if (Object.values(body).some(n => !Number.isInteger(n) || n < 0)) { setError('Nhập số nguyên không âm.'); return; }
    setBusy(true); setError('');
    try {
      await api(`/venues/${venueId}/booking-settings`, { method: 'PUT', body });
      toast('success', 'Đã lưu luật đặt bàn.');
      settings.reload();
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  if (!settings.data) return settings.error ? <ErrorState message={settings.error} onRetry={settings.reload} /> : <Skeleton height={120} />;
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });
  return (
    <Card>
      <form className="stack" onSubmit={save} noValidate>
        <h2>Luật đặt bàn và tiền cọc</h2>
        {settings.data.payment_is_mock && <p className="notice" role="note">Cọc đang ở chế độ mô phỏng: khách bấm "Trả cọc" chỉ đổi trạng thái trong hệ thống, không có tiền thật.</p>}
        <div className="grid-cards" style={{ alignItems: "start" }}>
          <Field label="Tiền cọc mỗi lượt (₫)" inputMode="numeric" value={form.deposit_amount} onChange={set('deposit_amount')} hint="0 = không cần cọc." />
          <Field label="Giữ chỗ chờ cọc (phút)" inputMode="numeric" value={form.hold_minutes} onChange={set('hold_minutes')} hint="Quá hạn lịch tự huỷ." />
          <Field label="Hoàn cọc nếu huỷ trước giờ hẹn (phút)" inputMode="numeric" value={form.refund_before_minutes} onChange={set('refund_before_minutes')} />
          <Field label="Chờ khách tới (phút)" inputMode="numeric" value={form.noshow_grace_minutes} onChange={set('noshow_grace_minutes')} hint="Sau mức này mới đánh dấu không đến." />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div><Button type="submit" variant="primary" loading={busy}>Lưu luật đặt bàn</Button></div>
      </form>
    </Card>
  );
}

type Action = { kind: 'check-in' | 'no-show' | 'cancel'; booking: BookingView } | null;

export function BookingsPage() {
  const { state } = useAuth();
  const toast = useToast();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const bookings = useLoad(() => api<BookingView[]>(`/venues/${venueId}/bookings`), [venueId]);
  const [action, setAction] = useState<Action>(null);

  async function run() {
    if (!action) return;
    const { kind, booking } = action;
    try {
      await api(`/venues/${venueId}/bookings/${booking.id}/${kind}`, { method: 'POST', body: {} });
      toast('success', kind === 'check-in' ? `Đã nhận bàn ${booking.table_name}. Phiên chơi đã được mở.` : kind === 'no-show' ? 'Đã đánh dấu khách không đến.' : 'Đã huỷ lịch và hoàn cọc.');
      bookings.reload();
    } catch (failure) { toast('error', (failure as Error).message); } finally { setAction(null); }
  }

  const text = {
    'check-in': { title: 'Nhận bàn cho khách?', body: 'Mở phiên chơi cho khách này. Tiền cọc sẽ được trừ vào hoá đơn khi tính tiền.', label: 'Nhận bàn', danger: false },
    'no-show': { title: 'Khách không đến?', body: 'Lịch đặt chuyển sang "Không đến" và quán giữ tiền cọc.', label: 'Đánh dấu không đến', danger: true },
    cancel: { title: 'Huỷ lịch đặt?', body: 'Quầy huỷ thì khách luôn được hoàn cọc.', label: 'Huỷ lịch đặt', danger: true },
  } as const;
  const current = action ? text[action.kind] : null;

  return (
    <>
      <div className="page-head"><h1>Đặt bàn</h1></div>
      {user?.role === 'owner' && <SettingsCard venueId={venueId} />}
      <div className="stack">
        <h2>Lịch sắp tới</h2>
        {bookings.error ? <Card><ErrorState message={bookings.error} onRetry={bookings.reload} /></Card>
          : !bookings.data ? <Skeleton height={160} />
          : (
            <DataTable rows={bookings.data} rowKey={b => b.id}
              empty={<EmptyState title="Chưa có lịch đặt" description="Khách đặt bàn trên trang riêng của quán sẽ hiện ở đây." />}
              columns={[
                { key: 'time', header: 'Giờ hẹn', render: b => dateTime(b.start_at) },
                { key: 'table', header: 'Bàn', render: b => <strong>{b.table_name}</strong> },
                { key: 'cust', header: 'Khách', render: b => b.customer ? `${b.customer.name} · ${b.customer.phone}` : '—' },
                { key: 'dep', header: 'Cọc', render: b => b.deposit ? `${money(b.deposit.amount)} · ${DEPOSIT_LABEL[b.deposit.status]}${b.deposit.is_mock ? ' (mô phỏng)' : ''}` : 'Không cọc' },
                { key: 'status', header: 'Trạng thái', render: b => <Badge tone={BOOKING_LABEL[b.status].tone}>{BOOKING_LABEL[b.status].text}</Badge> },
                { key: 'act', header: '', align: 'right', render: b => (
                  <div className="row" style={{ justifyContent: 'flex-end' }}>
                    {b.status === 'CONFIRMED' && <Button size="sm" variant="primary" onClick={() => setAction({ kind: 'check-in', booking: b })}>Nhận bàn</Button>}
                    {b.status === 'CONFIRMED' && <Button size="sm" variant="ghost" onClick={() => setAction({ kind: 'no-show', booking: b })}>Không đến</Button>}
                    {(b.status === 'CONFIRMED' || b.status === 'PENDING') && <Button size="sm" variant="ghost" onClick={() => setAction({ kind: 'cancel', booking: b })}>Huỷ</Button>}
                  </div>) },
              ]} />
          )}
      </div>
      <ConfirmDialog open={action !== null} title={current?.title ?? ''} description={current?.body ?? ''} confirmLabel={current?.label ?? ''}
        danger={current?.danger} onCancel={() => setAction(null)} onConfirm={() => void run()} />
    </>
  );
}
