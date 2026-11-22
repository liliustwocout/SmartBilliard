import { useState } from 'react';
import { api } from '../../api';
import type { BookingSettings, BookingView } from '../../api';
import { useAuth } from '../../auth';
import { dateTime, money } from '../../format';
import { BOOKING_LABEL, DEPOSIT_LABEL } from '../../labels';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Skeleton, useToast } from '../../ui/components';
import { DepositDialog } from '../../ui/DepositDialog';

export function MyBookingsPage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const bookings = useLoad(() => api<BookingView[]>(`/venues/${venueId}/my/bookings`), [venueId]);
  const settings = useLoad(() => api<BookingSettings>(`/venues/${venueId}/booking-settings`), [venueId]);
  const [paying, setPaying] = useState<BookingView | null>(null);
  const [cancelling, setCancelling] = useState<BookingView | null>(null);

  async function confirmCancel() {
    if (!cancelling) return;
    try {
      const result = await api<BookingView>(`/venues/${venueId}/my/bookings/${cancelling.id}/cancel`, { method: 'POST', body: {} });
      toast('success', result.deposit?.status === 'REFUNDED' ? 'Đã huỷ lịch đặt và hoàn cọc.' : 'Đã huỷ lịch đặt.');
      bookings.reload();
    } catch (failure) { toast('error', (failure as Error).message); } finally { setCancelling(null); }
  }

  function cancelText(b: BookingView): string {
    if (b.status === 'PENDING' || !b.deposit || b.deposit.status !== 'PAID') return 'Lịch đặt sẽ bị huỷ.';
    const limit = settings.data?.refund_before_minutes ?? 60;
    const refundable = Date.now() <= new Date(b.start_at).getTime() - limit * 60_000;
    return refundable ? `Bạn sẽ được hoàn cọc ${money(b.deposit.amount)}.` : `Còn dưới ${limit} phút tới giờ hẹn nên bạn sẽ mất cọc ${money(b.deposit.amount)}.`;
  }

  return (
    <>
      <h1>Lịch đặt của tôi</h1>
      {bookings.error ? <Card><ErrorState message={bookings.error} onRetry={bookings.reload} /></Card>
        : !bookings.data ? <Skeleton height={140} />
        : bookings.data.length === 0 ? <Card><EmptyState title="Bạn chưa đặt bàn nào" description="Chọn bàn và giờ ở mục Đặt bàn." action={<a className="btn btn-primary" href="#/">Đặt bàn</a>} /></Card>
        : (
          <div className="stack">
            {bookings.data.map(b => {
              const label = BOOKING_LABEL[b.status];
              return (
                <Card key={b.id} className="booking-card">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <h3>{b.table_name}</h3><Badge tone={label.tone}>{label.text}</Badge>
                  </div>
                  <p>{dateTime(b.start_at)} – {dateTime(b.end_at)}</p>
                  {b.deposit && <p className="muted">Cọc {money(b.deposit.amount)}: {DEPOSIT_LABEL[b.deposit.status]}{b.deposit.is_mock ? ' (mô phỏng)' : ''}</p>}
                  {b.status === 'PENDING' && b.expires_at && <p className="muted">Giữ chỗ tới {dateTime(b.expires_at)}</p>}
                  {(b.status === 'PENDING' || b.status === 'CONFIRMED') && (
                    <div className="row">
                      {b.status === 'PENDING' && <Button variant="primary" size="sm" onClick={() => setPaying(b)}>Trả cọc</Button>}
                      <Button size="sm" onClick={() => setCancelling(b)}>Huỷ lịch</Button>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      <DepositDialog venueId={venueId} booking={paying} onClose={() => setPaying(null)}
        onPaid={() => { setPaying(null); bookings.reload(); toast('success', 'Đã xác nhận lịch đặt.'); }} />
      <ConfirmDialog open={cancelling !== null} danger title="Huỷ lịch đặt này?" description={cancelling ? cancelText(cancelling) : ''}
        confirmLabel="Huỷ lịch đặt" onCancel={() => setCancelling(null)} onConfirm={() => void confirmCancel()} />
    </>
  );
}
