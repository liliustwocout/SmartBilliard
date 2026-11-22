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
      <h3>{data.venue_name}</h3>
      <p className="muted">Hoá đơn #{data.invoice_no} · {data.table_name}</p>
      <dl className="credentials">
        <dt>Bắt đầu</dt><dd>{dateTime(data.started_at)}</dd>
        <dt>Kết thúc</dt><dd>{dateTime(data.ended_at)}</dd>
        {data.customer && <><dt>Khách</dt><dd>{data.customer}</dd></>}
      </dl>
      <table className="data-table">
        <tbody>
          <tr><td>Giờ chơi ({data.billable_minutes} phút × {money(data.rate)}/giờ)</td><td className="right num">{money(data.table_amount)}</td></tr>
          {data.items.map(item => (
            <tr key={item.id}><td>{item.name} × {item.quantity}</td><td className="right num">{money(item.amount)}</td></tr>
          ))}
          <tr><td><strong>Tổng cộng</strong></td><td className="right num" data-testid="invoice-total" style={{ fontSize: 'var(--text-xl)' }}>{money(data.total)}</td></tr>
        </tbody>
      </table>
      <p className="muted">Thanh toán: {data.payment_method ? METHOD[data.payment_method] : '—'}{data.cashier ? ` · Thu ngân: ${data.cashier}` : ''}</p>
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
