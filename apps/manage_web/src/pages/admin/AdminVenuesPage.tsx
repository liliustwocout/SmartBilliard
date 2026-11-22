import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { CreatedVenue, Page, VenueSummary } from '../../api';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';
import { CredentialsDialog } from '../../ui/CredentialsDialog';

const PAGE = 20;

export function VenueStatusBadge({ status }: { status: VenueSummary['status'] }) {
  return status === 'ACTIVE' ? <Badge tone="ok">Hoạt động</Badge> : <Badge tone="danger">Tạm ngưng</Badge>;
}

function CreateVenueModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (created: CreatedVenue) => void }) {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [ownerLogin, setOwnerLogin] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) { setName(''); setSlug(''); setOwnerLogin(''); setOwnerName(''); setError(''); } }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !ownerLogin.trim() || !ownerName.trim()) { setError('Nhập tên quán, tên chủ quán và tên đăng nhập của chủ quán.'); return; }
    setBusy(true); setError('');
    try {
      onCreated(await api<CreatedVenue>('/admin/venues', {
        body: { name, slug: slug.trim() || null, owner: { login: ownerLogin, display_name: ownerName } },
      }));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Tạo quán mới" onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên quán" value={name} onChange={e => setName(e.target.value)} />
        <Field label="Địa chỉ quán (không bắt buộc)" value={slug} onChange={e => setSlug(e.target.value)}
          hint="Chữ thường, số, dấu gạch ngang. Để trống để tự tạo từ tên quán." />
        <Field label="Tên chủ quán" value={ownerName} onChange={e => setOwnerName(e.target.value)} />
        <Field label="Tên đăng nhập của chủ quán" value={ownerLogin} onChange={e => setOwnerLogin(e.target.value)} hint="Email hoặc số điện thoại." />
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" loading={busy}>Tạo quán</Button>
        </div>
      </form>
    </Modal>
  );
}

export function AdminVenuesPage() {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedVenue | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => { setDebounced(query); setPage(0); }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const { data, error, loading, reload } = useLoad(
    () => api<Page<VenueSummary>>(`/admin/venues?q=${encodeURIComponent(debounced)}&limit=${PAGE}&offset=${page * PAGE}`),
    [debounced, page],
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  return (
    <>
      <div className="page-head">
        <h1>Quán</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>Tạo quán</Button>
      </div>
      <div className="row">
        <div style={{ flex: '1 1 260px', maxWidth: 420 }}>
          <Field label="Tìm quán" placeholder="Tên hoặc địa chỉ quán" value={query} onChange={e => setQuery(e.target.value)} />
        </div>
      </div>
      {error ? <Card><ErrorState message={error} onRetry={reload} /></Card>
        : loading && !data ? <Skeleton height={220} />
        : (
          <DataTable rows={data?.items ?? []} rowKey={v => String(v.id)}
            empty={<EmptyState title={debounced ? 'Không có quán khớp tìm kiếm' : 'Chưa có quán nào'}
              description={debounced ? 'Thử từ khoá khác hoặc xoá bộ lọc.' : 'Tạo quán đầu tiên để cấp tài khoản cho chủ quán.'}
              action={debounced ? undefined : <Button variant="primary" onClick={() => setCreating(true)}>Tạo quán</Button>} />}
            columns={[
              { key: 'name', header: 'Quán', render: v => <a href={`#/venues/${v.id}`}><strong>{v.name}</strong></a> },
              { key: 'slug', header: 'Địa chỉ', render: v => <span className="num">{v.slug}</span> },
              { key: 'owner', header: 'Chủ quán', render: v => v.owner ? `${v.owner.display_name} (${v.owner.login})` : '—' },
              { key: 'staff', header: 'Nhân viên', align: 'right', render: v => <span className="num">{v.counts.staff}</span> },
              { key: 'customers', header: 'Khách', align: 'right', render: v => <span className="num">{v.counts.customers}</span> },
              { key: 'status', header: 'Trạng thái', render: v => <VenueStatusBadge status={v.status} /> },
              { key: 'created', header: 'Tạo lúc', render: v => dateTime(v.created_at) },
            ]} />
        )}
      {data && data.total > PAGE && (
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="muted">Trang {page + 1}/{pages} · {data.total} quán</span>
          <div className="row">
            <Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Trước</Button>
            <Button size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Sau</Button>
          </div>
        </div>
      )}

      <CreateVenueModal open={creating} onClose={() => setCreating(false)}
        onCreated={result => { setCreating(false); setCreated(result); reload(); toast('success', `Đã tạo quán ${result.venue.name}.`); }} />
      <CredentialsDialog open={created !== null} title="Tài khoản chủ quán" login={created?.venue.owner?.login ?? ''}
        password={created?.owner_temp_password ?? ''} onClose={() => setCreated(null)} />
    </>
  );
}
