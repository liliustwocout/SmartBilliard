import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../../api';
import type { StaffRow } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, Modal, Skeleton, useToast } from '../../ui/components';
import { CredentialsDialog } from '../../ui/CredentialsDialog';

function CreateStaffModal({ venueId, open, onClose, onCreated }:
  { venueId: number; open: boolean; onClose: () => void; onCreated: (login: string, password: string) => void }) {
  const [login, setLogin] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setLogin(''); setName(''); setError(''); } }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!login.trim() || !name.trim()) { setError('Nhập tên nhân viên và tên đăng nhập.'); return; }
    setBusy(true); setError('');
    try {
      const result = await api<{ staff: StaffRow; temp_password: string }>(`/venues/${venueId}/staff`, { body: { login, display_name: name } });
      onCreated(result.staff.login, result.temp_password);
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Thêm nhân viên" onClose={onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Tên nhân viên" value={name} onChange={e => setName(e.target.value)} />
        <Field label="Tên đăng nhập" value={login} onChange={e => setLogin(e.target.value)} hint="Email hoặc số điện thoại, tối thiểu 3 ký tự, không trùng với ai trong hệ thống." />
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" loading={busy}>Thêm nhân viên</Button>
        </div>
      </form>
    </Modal>
  );
}

export function StaffPage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const staff = useLoad(() => api<StaffRow[]>(`/venues/${venueId}/staff`), [venueId]);
  const [creating, setCreating] = useState(false);
  const [credentials, setCredentials] = useState<{ login: string; password: string } | null>(null);
  const [reset, setReset] = useState<StaffRow | null>(null);

  async function toggle(row: StaffRow) {
    const next = row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    try {
      await api(`/venues/${venueId}/staff/${row.id}`, { method: 'PATCH', body: { status: next } });
      toast('success', next === 'DISABLED' ? `Đã khoá ${row.display_name}.` : `Đã mở khoá ${row.display_name}.`);
      staff.reload();
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  async function confirmReset() {
    if (!reset) return;
    try {
      const result = await api<{ login: string; temp_password: string }>(`/venues/${venueId}/staff/${reset.id}/reset-password`, { method: 'POST', body: {} });
      setCredentials({ login: result.login, password: result.temp_password });
    } catch (failure) { toast('error', (failure as Error).message); } finally { setReset(null); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Nhân viên</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>Thêm nhân viên</Button>
      </div>
      {staff.error ? <Card><ErrorState message={staff.error} onRetry={staff.reload} /></Card>
        : !staff.data ? <Skeleton height={180} />
        : (
          <DataTable rows={staff.data} rowKey={s => String(s.id)}
            empty={<EmptyState title="Chưa có nhân viên" description="Thêm nhân viên để họ tự mở bàn và tính tiền. Nhân viên không đổi được giá hay xem doanh thu các ngày trước."
              action={<Button variant="primary" onClick={() => setCreating(true)}>Thêm nhân viên</Button>} />}
            columns={[
              { key: 'name', header: 'Nhân viên', render: s => <strong>{s.display_name}</strong> },
              { key: 'login', header: 'Đăng nhập', render: s => <span className="num">{s.login}</span> },
              { key: 'status', header: 'Trạng thái', render: s => s.status === 'DISABLED' ? <Badge tone="danger">Đã khoá</Badge> : s.must_change_password ? <Badge tone="warn">Chưa đổi mật khẩu tạm</Badge> : <Badge tone="ok">Hoạt động</Badge> },
              { key: 'created', header: 'Thêm lúc', render: s => dateTime(s.created_at) },
              { key: 'act', header: '', align: 'right', render: s => (
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" onClick={() => setReset(s)}>Đặt lại mật khẩu</Button>
                  <Button size="sm" variant={s.status === 'ACTIVE' ? 'danger' : 'secondary'} onClick={() => void toggle(s)}>{s.status === 'ACTIVE' ? 'Khoá' : 'Mở khoá'}</Button>
                </div>) },
            ]} />
        )}
      <CreateStaffModal venueId={venueId} open={creating} onClose={() => setCreating(false)}
        onCreated={(login, password) => { setCreating(false); setCredentials({ login, password }); staff.reload(); }} />
      <CredentialsDialog open={credentials !== null} title="Tài khoản nhân viên" recipient="nhân viên" login={credentials?.login ?? ''}
        password={credentials?.password ?? ''} onClose={() => setCredentials(null)} />
      <ConfirmDialog open={reset !== null} danger title={`Đặt lại mật khẩu của ${reset?.display_name ?? ''}?`}
        description="Nhân viên bị đăng xuất khỏi mọi thiết bị và phải đổi mật khẩu bằng mật khẩu tạm mới."
        confirmLabel="Đặt lại mật khẩu" onCancel={() => setReset(null)} onConfirm={() => void confirmReset()} />
    </>
  );
}
