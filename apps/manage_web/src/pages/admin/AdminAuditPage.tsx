import { api } from '../../api';
import type { AuditRow } from '../../api';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Button, DataTable, EmptyState, ErrorState, Skeleton } from '../../ui/components';

export const ACTION_LABEL: Record<string, string> = {
  login_ok: 'Đăng nhập', login_failed: 'Đăng nhập sai', login_blocked_locked: 'Đăng nhập bị chặn (đang khoá)',
  login_blocked_disabled: 'Đăng nhập bị chặn (tài khoản khoá)', account_locked: 'Khoá tạm do nhập sai nhiều lần',
  logout: 'Đăng xuất', password_changed: 'Đổi mật khẩu', admin_created: 'Tạo admin', venue_created: 'Tạo quán',
  venue_updated: 'Cập nhật quán', owner_password_reset: 'Đặt lại mật khẩu chủ quán', user_status_changed: 'Đổi trạng thái tài khoản',
};

export function AdminAuditPage() {
  const { data, error, loading, reload } = useLoad(() => api<AuditRow[]>('/admin/audit?limit=200'), []);
  return (
    <>
      <div className="page-head">
        <h1>Nhật ký hoạt động</h1>
        <Button onClick={reload} loading={loading && data !== null}>Tải lại</Button>
      </div>
      {error ? <ErrorState message={error} onRetry={reload} />
        : !data ? <Skeleton height={240} />
        : (
          <DataTable rows={data} rowKey={r => String(r.id)}
            empty={<EmptyState title="Chưa có hoạt động" description="Đăng nhập, tạo quán và đổi trạng thái tài khoản sẽ được ghi tại đây." />}
            columns={[
              { key: 'at', header: 'Thời gian', render: r => dateTime(r.at) },
              { key: 'action', header: 'Hành động', render: r => ACTION_LABEL[r.action] ?? r.action },
              { key: 'target', header: 'Đối tượng', render: r => r.target ?? '—' },
              { key: 'actor', header: 'Người thực hiện', render: r => r.actor_login ?? '—' },
            ]} />
        )}
    </>
  );
}
