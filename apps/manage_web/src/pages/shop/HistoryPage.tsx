import { useState } from 'react';
import { api } from '../../api';
import type { Page, SessionView } from '../../api';
import { useAuth } from '../../auth';
import { dateTime, duration, money } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, SelectField, Skeleton } from '../../ui/components';
import { InvoiceDialog } from '../../ui/InvoiceDialog';

const PAGE = 25;
type StatusFilter = '' | 'ACTIVE' | 'PAID' | 'VOID';

function StatusBadge({ status }: { status: SessionView['status'] }) {
  if (status === 'PAID') return <Badge tone="ok">Đã thanh toán</Badge>;
  if (status === 'ACTIVE') return <Badge tone="warn">Đang chơi</Badge>;
  return <Badge tone="danger">Đã huỷ</Badge>;
}

export function HistoryPage() {
  const { state } = useAuth();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const isOwner = user?.role === 'owner';
  const [status, setStatus] = useState<StatusFilter>('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(0);
  const [invoiceFor, setInvoiceFor] = useState<string | null>(null);

  const query = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
  if (status) query.set('status', status);
  if (isOwner && from) query.set('date_from', from);
  if (isOwner && to) query.set('date_to', to);
  const { data, error, loading, reload } = useLoad(
    () => api<Page<SessionView>>(`/venues/${venueId}/sessions?${query.toString()}`), [venueId, status, from, to, page]);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  return (
    <>
      <div className="page-head"><h1>Lịch sử phiên</h1></div>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <SelectField label="Trạng thái" value={status} onChange={e => { setStatus(e.target.value as StatusFilter); setPage(0); }}>
          <option value="">Tất cả</option><option value="PAID">Đã thanh toán</option><option value="ACTIVE">Đang chơi</option><option value="VOID">Đã huỷ</option>
        </SelectField>
        {isOwner && <>
          <Field label="Từ ngày" type="date" value={from} onChange={e => { setFrom(e.target.value); setPage(0); }} />
          <Field label="Đến ngày" type="date" value={to} onChange={e => { setTo(e.target.value); setPage(0); }} />
        </>}
      </div>
      {!isOwner && <p className="muted">Nhân viên chỉ xem được các phiên của hôm nay.</p>}
      {error ? <Card><ErrorState message={error} onRetry={reload} /></Card>
        : !data ? <Skeleton height={220} />
        : (
          <DataTable rows={data.items} rowKey={s => s.id}
            empty={<EmptyState title="Chưa có phiên nào" description={isOwner ? 'Không có phiên khớp bộ lọc.' : 'Hôm nay chưa có phiên chơi nào.'} />}
            columns={[
              { key: 'table', header: 'Bàn', render: s => <strong>{s.table_name ?? '—'}</strong> },
              { key: 'start', header: 'Bắt đầu', render: s => dateTime(s.started_at) },
              { key: 'end', header: 'Kết thúc', render: s => dateTime(s.ended_at) },
              { key: 'dur', header: 'Thời gian', render: s => <span className="num">{duration(s.elapsed_seconds)}</span> },
              { key: 'status', header: 'Trạng thái', render: s => <StatusBadge status={s.status} /> },
              { key: 'amount', header: 'Tiền', align: 'right', render: s => <span className="num">{s.status === 'VOID' ? '—' : money(s.amount_vnd)}</span> },
              { key: 'invoice', header: '', align: 'right', render: s => s.status === 'PAID' ? <Button size="sm" variant="ghost" onClick={() => setInvoiceFor(s.id)}>Hoá đơn</Button> : null },
            ]} />
        )}
      {data && data.total > PAGE && (
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="muted">Trang {page + 1}/{pages} · {data.total} phiên</span>
          <div className="row">
            <Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Trước</Button>
            <Button size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Sau</Button>
          </div>
        </div>
      )}
      <InvoiceDialog venueId={venueId} sessionId={invoiceFor} onClose={() => setInvoiceFor(null)} />
    </>
  );
}
