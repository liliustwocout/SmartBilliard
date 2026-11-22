import { api } from '../api';
import type { Invoice } from '../api';
import { dateTime, money } from '../format';
import { useLoad } from '../useLoad';
import { Button, ErrorState, Modal, Skeleton } from './components';

const METHOD: Record<string, string> = { cash: 'Tiền mặt', transfer: 'Chuyển khoản' };

function InvoiceBody({ venueId, sessionId }: { venueId: number; sessionId: string }) {
  const { data, error, reload } = useLoad(() => api<Invoice>(`/venues/${venueId}/sessions/${sessionId}/invoice`), [venueId, sessionId]);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Skeleton height={200} />;
  return (
    <div className="invoice" data-testid="invoice">
      <header className="invoice-head">
        <h3>{data.venue_name}</h3>
        <p className="invoice-kicker">HOÁ ĐƠN THANH TOÁN</p>
        <p className="muted">#{data.invoice_no} · {data.table_name}</p>
      </header>
      <dl className="invoice-meta">
        <dt>Bắt đầu</dt><dd>{dateTime(data.started_at)}</dd>
        <dt>Kết thúc</dt><dd>{dateTime(data.ended_at)}</dd>
        {data.customer && <><dt>Khách</dt><dd>{data.customer}</dd></>}
      </dl>
      <table className="invoice-lines">
        <thead><tr><th>Khoản</th><th className="right">Thành tiền</th></tr></thead>
        <tbody>
          <tr><td>Giờ chơi<small>{data.billable_minutes} phút × {money(data.rate)}/giờ</small></td><td className="right num">{money(data.table_amount)}</td></tr>
          {data.items.map(item => (
            <tr key={item.id}><td>{item.name} × {item.quantity}<small>{money(item.unit_price)} / đơn vị</small></td><td className="right num">{money(item.amount)}</td></tr>
          ))}
        </tbody>
        <tfoot>
          {data.voucher_discount > 0 && <tr><td>Voucher</td><td className="right num">− {money(data.voucher_discount)}</td></tr>}
          <tr className="invoice-total"><td>Tổng cộng</td><td className="right num" data-testid="invoice-total">{money(data.total)}</td></tr>
          {data.deposit_applied > 0 && <>
            <tr><td>Đã cọc (mô phỏng)</td><td className="right num">− {money(data.deposit_applied)}</td></tr>
            <tr className="invoice-total"><td>Còn phải thu</td><td className="right num" data-testid="invoice-due">{money(data.amount_due)}</td></tr>
          </>}
        </tfoot>
      </table>
      <p className="invoice-foot">Thanh toán: {data.payment_method ? METHOD[data.payment_method] : '—'}{data.cashier ? ` · Thu ngân: ${data.cashier}` : ''}</p>
      <p className="invoice-thanks">Cảm ơn quý khách, hẹn gặp lại!</p>
    </div>
  );
}

/** Hoá đơn của phiên đã thanh toán; "In hoá đơn" chỉ in khối hoá đơn (xem @media print). */
export function InvoiceDialog({ venueId, sessionId, onClose }: { venueId: number; sessionId: string | null; onClose: () => void }) {
  return (
    <Modal open={sessionId !== null} title="Hoá đơn" onClose={onClose}
      actions={<><Button onClick={onClose}>Đóng</Button><Button variant="primary" onClick={() => window.print()}>In hoá đơn</Button></>}>
      {sessionId && <InvoiceBody venueId={venueId} sessionId={sessionId} />}
    </Modal>
  );
}
