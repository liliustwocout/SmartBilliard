import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { CustomerRow, Page, VenueSummary } from '../../api';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, Skeleton, useToast } from '../../ui/components';
import { CredentialsDialog } from '../../ui/CredentialsDialog';
import { VenueStatusBadge } from './AdminVenuesPage';

type Pending = 'suspend' | 'activate' | 'reset' | null;

export function AdminVenueDetailPage({ venueId }: { venueId: number }) {
  const toast = useToast();
  const venue = useLoad(() => api<VenueSummary>(`/admin/venues/${venueId}`), [venueId]);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);
  const customers = useLoad(() => api<Page<CustomerRow>>(`/admin/venues/${venueId}/customers?q=${encodeURIComponent(debounced)}&limit=100`), [venueId, debounced]);

  const [pending, setPending] = useState<Pending>(null);
  const [credentials, setCredentials] = useState<{ login: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    try { await work(); } catch (reason) { toast('error', (reason as Error).message); } finally { setBusy(false); setPending(null); }
  }

  const confirmAction = () => run(async () => {
    if (pending === 'reset') {
      const result = await api<{ owner_login: string; owner_temp_password: string }>(`/admin/venues/${venueId}/owner/reset-password`, { method: 'POST', body: {} });
      setCredentials({ login: result.owner_login, password: result.owner_temp_password });
    } else {
      await api(`/admin/venues/${venueId}`, { method: 'PATCH', body: { status: pending === 'suspend' ? 'SUSPENDED' : 'ACTIVE' } });
      toast('success', pending === 'suspend' ? 'Đã tạm ngưng quán.' : 'Đã mở lại quán.');
    }
    venue.reload();
  });

  async function toggleCustomer(row: CustomerRow) {
    const next = row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    await run(async () => {
      await api(`/admin/users/${row.id}/status`, { method: 'PATCH', body: { status: next } });
      toast('success', next === 'DISABLED' ? 'Đã khoá tài khoản khách.' : 'Đã mở khoá tài khoản khách.');
      customers.reload();
    });
  }

  if (venue.error) return <Card><ErrorState message={venue.error} onRetry={venue.reload} /></Card>;
  if (!venue.data) return <Skeleton height={160} />;
  const v = venue.data;

  const dialog = {
    suspend: { title: `Tạm ngưng ${v.name}?`, description: 'Chủ quán, nhân viên và khách của quán sẽ bị đăng xuất và không đăng nhập được cho tới khi mở lại. Dữ liệu được giữ nguyên.', label: 'Tạm ngưng quán', danger: true },
    activate: { title: `Mở lại ${v.name}?`, description: 'Mọi tài khoản của quán có thể đăng nhập trở lại.', label: 'Mở lại quán', danger: false },
    reset: { title: 'Đặt lại mật khẩu chủ quán?', description: 'Chủ quán bị đăng xuất khỏi mọi thiết bị và phải đổi mật khẩu bằng mật khẩu tạm mới.', label: 'Đặt lại mật khẩu', danger: true },
  } as const;
  const current = pending ? dialog[pending] : null;

  return (
    <>
      <div className="page-head">
        <div className="stack" style={{ gap: 6 }}>
          <a href="#/venues">← Danh sách quán</a>
          <h1>{v.name}</h1>
          <div className="row"><VenueStatusBadge status={v.status} /><span className="num muted">/{v.slug}</span><span className="muted">Tạo {dateTime(v.created_at)}</span></div>
        </div>
        <div className="row">
          <Button onClick={() => setPending('reset')} disabled={!v.owner}>Đặt lại mật khẩu chủ quán</Button>
          {v.status === 'ACTIVE'
            ? <Button variant="danger" onClick={() => setPending('suspend')}>Tạm ngưng quán</Button>
            : <Button variant="primary" onClick={() => setPending('activate')}>Mở lại quán</Button>}
        </div>
      </div>

      <div className="grid-cards">
        <Card flat><div className="muted">Chủ quán</div>
          <strong>{v.owner?.display_name ?? '—'}</strong>
          <div className="num muted">{v.owner?.login}</div>
          {v.owner?.must_change_password && <Badge tone="warn">Chưa đổi mật khẩu tạm</Badge>}
        </Card>
        <Card flat><div className="muted">Nhân viên</div><div className="num stat">{v.counts.staff}</div></Card>
        <Card flat><div className="muted">Khách hàng</div><div className="num stat">{v.counts.customers}</div></Card>
      </div>

      <div className="stack">
        <h2>Khách của quán</h2>
        <div style={{ maxWidth: 420 }}>
          <Field label="Tìm khách" placeholder="Tên hoặc số điện thoại" value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        {customers.error ? <ErrorState message={customers.error} onRetry={customers.reload} /> : (
          <DataTable rows={customers.data?.items ?? []} rowKey={c => String(c.id)}
            empty={<EmptyState title={debounced ? 'Không có khách khớp' : 'Quán chưa có khách'} description={debounced ? 'Thử từ khoá khác.' : 'Khách tự đăng ký tại trang riêng của quán sẽ hiện ở đây.'} />}
            columns={[
              { key: 'name', header: 'Tên', render: c => c.display_name },
              { key: 'login', header: 'Đăng nhập', render: c => <span className="num">{c.login}</span> },
              { key: 'status', header: 'Trạng thái', render: c => c.status === 'ACTIVE' ? <Badge tone="ok">Bình thường</Badge> : <Badge tone="danger">Đã khoá</Badge> },
              { key: 'created', header: 'Đăng ký', render: c => dateTime(c.created_at) },
              { key: 'act', header: '', align: 'right', render: c => (
                <Button size="sm" variant={c.status === 'ACTIVE' ? 'danger' : 'secondary'} disabled={busy} onClick={() => void toggleCustomer(c)}>
                  {c.status === 'ACTIVE' ? 'Khoá' : 'Mở khoá'}
                </Button>) },
            ]} />
        )}
      </div>

      <ConfirmDialog open={current !== null} title={current?.title ?? ''} description={current?.description ?? ''}
        confirmLabel={current?.label ?? ''} danger={current?.danger} onCancel={() => setPending(null)} onConfirm={() => void confirmAction()} />
      <CredentialsDialog open={credentials !== null} title="Mật khẩu tạm mới" login={credentials?.login ?? ''}
        password={credentials?.password ?? ''} onClose={() => setCredentials(null)} />
    </>
  );
}
