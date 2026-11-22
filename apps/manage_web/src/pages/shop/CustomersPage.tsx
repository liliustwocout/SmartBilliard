import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import QRCode from 'qrcode';
import { api } from '../../api';
import type { CustomerRow, Page } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';
import { CredentialsDialog } from '../../ui/CredentialsDialog';

const DEFAULT_PASSWORD = '1234567890';

function CustomerLinkCard({ slug }: { slug: string }) {
  const toast = useToast();
  const link = `${window.location.origin}${window.location.pathname}#/c/${slug}`;
  const [qr, setQr] = useState('');
  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(link, { width: 280, margin: 2, errorCorrectionLevel: 'M' }).then(url => { if (!cancelled) setQr(url); }).catch(() => { if (!cancelled) setQr(''); });
    return () => { cancelled = true; };
  }, [link]);
  async function copy() {
    try { await navigator.clipboard.writeText(link); toast('success', 'Đã sao chép link trang khách.'); }
    catch { toast('error', 'Không sao chép được. Hãy chọn và sao chép link thủ công.'); }
  }
  return (
    <Card flat>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 320px' }}>
          <Field label="Link trang khách của quán" readOnly value={link} onFocus={e => e.currentTarget.select()}
            hint="Gửi link này cho khách để tự đăng ký, đặt bàn và check-in nhận thưởng." />
        </div>
        <Button onClick={() => void copy()}>Sao chép link</Button>
        <a className="btn btn-secondary" href={link} target="_blank" rel="noreferrer">Mở thử</a>
      </div>
      {qr && (
        <div className="row" style={{ alignItems: 'center', marginTop: 'var(--space-3)' }}>
          <img src={qr} alt={`Mã QR trang khách ${slug}`} width={140} height={140} style={{ background: '#fff', borderRadius: 'var(--radius-md)' }} />
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            <span className="muted">Khách quét mã bằng điện thoại để vào trang của quán. In ra dán ở quầy hoặc bàn.</span>
            <a className="btn btn-secondary" href={qr} download={`qr-${slug}.png`}>Tải ảnh QR</a>
          </div>
        </div>
      )}
    </Card>
  );
}

function CreateCustomerModal({ venueId, open, onClose, onCreated }:
  { venueId: number; open: boolean; onClose: () => void; onCreated: (phone: string, password: string) => void }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState(DEFAULT_PASSWORD);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(''); setPhone(''); setPassword(DEFAULT_PASSWORD); setError(''); } }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !phone.trim()) { setError('Nhập tên khách và số điện thoại.'); return; }
    setBusy(true); setError('');
    try {
      const result = await api<{ customer: CustomerRow; temp_password: string }>(`/venues/${venueId}/customers`, { body: { display_name: name, phone, password: password || null } });
      onCreated(result.customer.login, result.temp_password);
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Thêm khách" onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên khách" value={name} onChange={e => setName(e.target.value)} />
        <Field label="Số điện thoại" inputMode="tel" value={phone} onChange={e => setPhone(e.target.value)} hint="Dùng làm tên đăng nhập của khách tại quán này." />
        <Field label="Mật khẩu ban đầu" value={password} onChange={e => setPassword(e.target.value)} autoComplete="off"
          hint="Mặc định là mật khẩu gốc. Khách phải đổi mật khẩu khi đăng nhập lần đầu." />
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

  async function resetPassword(row: CustomerRow) {
    if (!window.confirm(`Đặt lại mật khẩu của ${row.display_name} về mật khẩu gốc? Khách sẽ bị đăng xuất và phải đổi mật khẩu khi vào lại.`)) return;
    try {
      const result = await api<{ login: string; temp_password: string }>(`/venues/${venueId}/customers/${row.id}/reset-password`, { body: {} });
      setCredentials({ login: result.login, password: result.temp_password });
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Khách hàng</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>Thêm khách</Button>
      </div>
      {user?.venue?.slug && <CustomerLinkCard slug={user.venue.slug} />}
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
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" variant="secondary" onClick={() => void resetPassword(c)}>Đặt lại mật khẩu</Button>
                  <Button size="sm" variant={c.status === 'ACTIVE' ? 'danger' : 'secondary'} onClick={() => void toggle(c)}>{c.status === 'ACTIVE' ? 'Khoá' : 'Mở khoá'}</Button>
                </div>) }] : []),
            ]} />
        )}
      <CreateCustomerModal venueId={venueId} open={creating} onClose={() => setCreating(false)}
        onCreated={(phone, password) => { setCreating(false); setCredentials({ login: phone, password }); customers.reload(); }} />
      <CredentialsDialog open={credentials !== null} title="Tài khoản khách" recipient="khách" login={credentials?.login ?? ''}
        password={credentials?.password ?? ''} onClose={() => setCredentials(null)} />
    </>
  );
}
