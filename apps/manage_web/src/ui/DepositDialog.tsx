import { useState } from 'react';
import { api } from '../api';
import type { BookingView } from '../api';
import { dateTime, money } from '../format';
import { Button, Modal } from './components';

/** Trả cọc GIẢ LẬP: bấm nút chỉ đổi trạng thái trong hệ thống, không thu tiền thật. */
export function DepositDialog({ venueId, booking, onClose, onPaid }:
  { venueId: number; booking: BookingView | null; onClose: () => void; onPaid: (booking: BookingView) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function pay() {
    if (!booking) return;
    setBusy(true); setError('');
    try { onPaid(await api<BookingView>(`/venues/${venueId}/my/bookings/${booking.id}/deposit/mock-pay`, { method: 'POST', body: {} })); }
    catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={booking !== null} title="Trả tiền cọc" onClose={onClose}
      actions={<><Button variant="ghost" onClick={onClose}>Để sau</Button>
        <Button variant="primary" loading={busy} onClick={() => void pay()}>Trả cọc (mô phỏng)</Button></>}>
      {booking?.deposit && (
        <>
          <p className="notice" role="note">Chế độ mô phỏng: không có khoản tiền thật nào bị trừ.</p>
          <dl className="credentials">
            <dt>Bàn</dt><dd>{booking.table_name}</dd>
            <dt>Giờ hẹn</dt><dd>{dateTime(booking.start_at)}</dd>
            <dt>Tiền cọc</dt><dd className="num" data-testid="deposit-amount">{money(booking.deposit.amount)}</dd>
          </dl>
          {booking.expires_at && <p className="muted">Quán giữ chỗ cho bạn tới {dateTime(booking.expires_at)}. Quá giờ này lịch đặt sẽ tự hết hạn.</p>}
        </>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
    </Modal>
  );
}
