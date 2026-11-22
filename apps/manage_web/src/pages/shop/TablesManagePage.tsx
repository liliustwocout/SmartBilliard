import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { TableRow, TableType, TablesResponse } from '../../api';
import { useAuth } from '../../auth';
import { money } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, Modal, SelectField, Skeleton, useToast } from '../../ui/components';

export const TYPE_LABEL: Record<TableType, string> = { pool: 'Pool', carom: 'Carom', snooker: 'Snooker', other: 'Khác' };

function TableModal({ venueId, editing, open, onClose, onSaved }:
  { venueId: number; editing: TableRow | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState<TableType>('pool');
  const [rate, setRate] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? ''); setType(editing?.table_type ?? 'pool'); setRate(editing ? String(editing.hourly_rate) : ''); setError('');
  }, [open, editing]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const hourly = Number(rate);
    if (!name.trim()) { setError('Nhập tên bàn.'); return; }
    if (!rate.trim() || !Number.isInteger(hourly) || hourly < 0 || hourly > 10_000_000) { setError('Giá giờ là số nguyên từ 0 đến 10.000.000 ₫.'); return; }
    setBusy(true); setError('');
    try {
      const body = { name, table_type: type, hourly_rate: hourly };
      if (editing) await api(`/venues/${venueId}/tables/${editing.id}`, { method: 'PATCH', body });
      else await api(`/venues/${venueId}/tables`, { body });
      onSaved();
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title={editing ? `Sửa ${editing.name}` : 'Thêm bàn'} onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên bàn" value={name} onChange={e => setName(e.target.value)} placeholder="Ví dụ: Bàn 01" />
        <SelectField label="Loại bàn" value={type} onChange={e => setType(e.target.value as TableType)}>
          {(Object.keys(TYPE_LABEL) as TableType[]).map(key => <option key={key} value={key}>{TYPE_LABEL[key]}</option>)}
        </SelectField>
        <Field label="Giá giờ (₫)" inputMode="numeric" value={rate} onChange={e => setRate(e.target.value)}
          hint={editing ? 'Giá mới chỉ áp dụng cho phiên mở sau; phiên đang chơi giữ giá cũ.' : 'Tính theo phút, làm tròn lên phút.'} />
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" loading={busy}>{editing ? 'Lưu thay đổi' : 'Thêm bàn'}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function TablesManagePage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const tables = useLoad(() => api<TablesResponse>(`/venues/${venueId}/tables`), [venueId]);
  const [modal, setModal] = useState<{ open: boolean; editing: TableRow | null }>({ open: false, editing: null });

  async function toggle(table: TableRow) {
    const next = table.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    try {
      await api(`/venues/${venueId}/tables/${table.id}`, { method: 'PATCH', body: { status: next } });
      toast('success', next === 'INACTIVE' ? `Đã ngừng dùng ${table.name}.` : `Đã dùng lại ${table.name}.`);
      tables.reload();
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Bàn và giá</h1>
        <Button variant="primary" onClick={() => setModal({ open: true, editing: null })}>Thêm bàn</Button>
      </div>
      {tables.error ? <Card><ErrorState message={tables.error} onRetry={tables.reload} /></Card>
        : !tables.data ? <Skeleton height={200} />
        : (
          <DataTable rows={tables.data.tables} rowKey={t => String(t.id)}
            empty={<EmptyState title="Chưa có bàn" description="Thêm bàn đầu tiên và đặt giá giờ." action={<Button variant="primary" onClick={() => setModal({ open: true, editing: null })}>Thêm bàn</Button>} />}
            columns={[
              { key: 'name', header: 'Bàn', render: t => <strong>{t.name}</strong> },
              { key: 'type', header: 'Loại', render: t => TYPE_LABEL[t.table_type] },
              { key: 'rate', header: 'Giá giờ', align: 'right', render: t => <span className="num">{money(t.hourly_rate)}</span> },
              { key: 'status', header: 'Trạng thái', render: t => t.session ? <Badge tone="warn">Đang chơi</Badge> : t.status === 'ACTIVE' ? <Badge tone="ok">Sẵn sàng</Badge> : <Badge>Ngừng dùng</Badge> },
              { key: 'act', header: '', align: 'right', render: t => (
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" onClick={() => setModal({ open: true, editing: t })}>Sửa</Button>
                  <Button size="sm" variant="ghost" disabled={t.session !== null} onClick={() => void toggle(t)}>{t.status === 'ACTIVE' ? 'Ngừng dùng' : 'Dùng lại'}</Button>
                </div>) },
            ]} />
        )}
      <TableModal venueId={venueId} editing={modal.editing} open={modal.open} onClose={() => setModal({ open: false, editing: null })}
        onSaved={() => { setModal({ open: false, editing: null }); tables.reload(); toast('success', 'Đã lưu bàn.'); }} />
    </>
  );
}
