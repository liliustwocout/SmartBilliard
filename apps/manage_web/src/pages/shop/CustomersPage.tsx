import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { CustomerRow, Page } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';
import { CredentialsDialog } from '../../ui/CredentialsDialog';

function CreateCustomerModal({ venueId, open, onClose, onCreated }:
  { venueId: number; open: boolean; onClose: () => void; onCreated: (phone: string, password: string) => void }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(''); setPhone(''); setError(''); } }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !phone.trim()) { setError('Nhập tên khách và số điện thoại.'); return; }
    setBusy(true); setError('');
    try {
      const result = await api<{ customer: CustomerRow; temp_password: string }>(`/venues/${venueId}/customers`, { body: { display_name: name, phone } });
      onCreated(result.customer.login, result.temp_password);
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Thêm khách" onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên khách" value={name} onChange={e => setName(e.target.value)} />
        <Field label="Số điện thoại" inputMode="tel" value={phone} onChange={e => setPhone(e.target.value)} hint="Dùng làm tên đăng nhập của khách tại quán này." />
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" loading={busy}>Thêm khách</Button>
        </div>
      </form>
    </Modal>
  );
}

export function CustomersPage() {
  const { state } = useAuth();
  const toast = useToast();
  const user = state.status === 'ready' ? state.user : null;
  const venueId = user?.venue?.id ?? 0;
  const isOwner = user?.role === 'owner';
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [creating, setCreating] = useState(false);
  const [credentials, setCredentials] = useState<{ login: string; password: string } | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);
  const customers = useLoad(() => api<Page<CustomerRow>>(`/venues/${venueId}/customers?q=${encodeURIComponent(debounced)}&limit=100`), [venueId, debounced]);

  async function toggle(row: CustomerRow) {
    const next = row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    try {
      await api(`/venues/${venueId}/customers/${row.id}/status`, { method: 'PATCH', body: { status: next } });
      toast('success', next === 'DISABLED' ? 'Đã khoá tài khoản khách.' : 'Đã mở khoá tài khoản khách.');
      customers.reload();
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Khách hàng</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>Thêm khách</Button>
      </div>
      <div style={{ maxWidth: 420 }}>
        <Field label="Tìm khách" placeholder="Tên hoặc số điện thoại" value={query} onChange={e => setQuery(e.target.value)} />
      </div>
      {customers.error ? <Card><ErrorState message={customers.error} onRetry={customers.reload} /></Card>
        : !customers.data ? <Skeleton height={180} />
        : (
          <DataTable rows={customers.data.items} rowKey={c => String(c.id)}
            empty={<EmptyState title={debounced ? 'Không có khách khớp' : 'Quán chưa có khách'} description={debounced ? 'Thử từ khoá khác.' : 'Thêm khách tại quầy hoặc để khách tự đăng ký ở bản tới.'} />}
            columns={[
              { key: 'name', header: 'Tên', render: c => <strong>{c.display_name}</strong> },
              { key: 'login', header: 'Số điện thoại', render: c => <span className="num">{c.login}</span> },
              { key: 'status', header: 'Trạng thái', render: c => c.status === 'ACTIVE' ? <Badge tone="ok">Bình thường</Badge> : <Badge tone="danger">Đã khoá</Badge> },
              { key: 'created', header: 'Đăng ký', render: c => dateTime(c.created_at) },
              ...(isOwner ? [{ key: 'act', header: '', align: 'right' as const, render: (c: CustomerRow) => (
                <Button size="sm" variant={c.status === 'ACTIVE' ? 'danger' : 'secondary'} onClick={() => void toggle(c)}>{c.status === 'ACTIVE' ? 'Khoá' : 'Mở khoá'}</Button>) }] : []),
            ]} />
        )}
      <CreateCustomerModal venueId={venueId} open={creating} onClose={() => setCreating(false)}
        onCreated={(phone, password) => { setCreating(false); setCredentials({ login: phone, password }); customers.reload(); }} />
      <CredentialsDialog open={credentials !== null} title="Tài khoản khách" recipient="khách" login={credentials?.login ?? ''}
        password={credentials?.password ?? ''} onClose={() => setCredentials(null)} />
    </>
  );
}
