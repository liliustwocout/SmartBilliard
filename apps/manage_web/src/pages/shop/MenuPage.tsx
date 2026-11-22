import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { ProductRow } from '../../api';
import { useAuth } from '../../auth';
import { money } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';

function ProductModal({ venueId, editing, open, onClose, onSaved }:
  { venueId: number; editing: ProductRow | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(editing?.name ?? ''); setPrice(editing ? String(editing.price) : ''); setError(''); } }, [open, editing]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = Number(price);
    if (!name.trim()) { setError('Nhập tên món.'); return; }
    if (!price.trim() || !Number.isInteger(value) || value < 0 || value > 10_000_000) { setError('Giá là số nguyên từ 0 đến 10.000.000 ₫.'); return; }
    setBusy(true); setError('');
    try {
      const body = { name, price: value };
      if (editing) await api(`/venues/${venueId}/products/${editing.id}`, { method: 'PATCH', body });
      else await api(`/venues/${venueId}/products`, { body });
      onSaved();
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title={editing ? `Sửa ${editing.name}` : 'Thêm món'} onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên món" value={name} onChange={e => setName(e.target.value)} placeholder="Ví dụ: Nước suối" />
        <Field label="Giá bán (₫)" inputMode="numeric" value={price} onChange={e => setPrice(e.target.value)}
          hint={editing ? 'Giá mới chỉ áp dụng cho món thêm sau; các dòng đã thêm giữ giá cũ.' : undefined} />
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" loading={busy}>{editing ? 'Lưu thay đổi' : 'Thêm món'}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function MenuPage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const products = useLoad(() => api<ProductRow[]>(`/venues/${venueId}/products`), [venueId]);
  const [modal, setModal] = useState<{ open: boolean; editing: ProductRow | null }>({ open: false, editing: null });

  async function toggle(row: ProductRow) {
    const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    try {
      await api(`/venues/${venueId}/products/${row.id}`, { method: 'PATCH', body: { status: next } });
      toast('success', next === 'INACTIVE' ? `Đã ngừng bán ${row.name}.` : `Đã bán lại ${row.name}.`);
      products.reload();
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  const add = () => setModal({ open: true, editing: null });
  return (
    <>
      <div className="page-head">
        <h1>Menu dịch vụ</h1>
        <Button variant="primary" onClick={add}>Thêm món</Button>
      </div>
      {products.error ? <Card><ErrorState message={products.error} onRetry={products.reload} /></Card>
        : !products.data ? <Skeleton height={180} />
        : (
          <DataTable rows={products.data} rowKey={r => String(r.id)}
            empty={<EmptyState title="Menu đang trống" description="Thêm nước uống, phấn, đồ ăn nhẹ để nhân viên cộng vào hoá đơn của bàn." action={<Button variant="primary" onClick={add}>Thêm món</Button>} />}
            columns={[
              { key: 'name', header: 'Món', render: r => <strong>{r.name}</strong> },
              { key: 'price', header: 'Giá', align: 'right', render: r => <span className="num">{money(r.price)}</span> },
              { key: 'status', header: 'Trạng thái', render: r => r.status === 'ACTIVE' ? <Badge tone="ok">Đang bán</Badge> : <Badge>Ngừng bán</Badge> },
              { key: 'act', header: '', align: 'right', render: r => (
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" onClick={() => setModal({ open: true, editing: r })}>Sửa</Button>
                  <Button size="sm" variant="ghost" onClick={() => void toggle(r)}>{r.status === 'ACTIVE' ? 'Ngừng bán' : 'Bán lại'}</Button>
                </div>) },
            ]} />
        )}
      <ProductModal venueId={venueId} editing={modal.editing} open={modal.open} onClose={() => setModal({ open: false, editing: null })}
        onSaved={() => { setModal({ open: false, editing: null }); products.reload(); toast('success', 'Đã lưu món.'); }} />
    </>
  );
}
