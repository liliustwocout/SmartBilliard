import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { AuditRow, Page, VenueSummary } from '../../api';
import { dateTime, todayVN } from '../../format';
import { useLoad } from '../../useLoad';
import { Button, DataTable, EmptyState, ErrorState, Field, Skeleton } from '../../ui/components';
import { Combobox } from '../../ui/Combobox';

export const ACTION_LABEL: Record<string, string> = {
  login_ok: 'Đăng nhập', login_failed: 'Đăng nhập sai', login_blocked_locked: 'Đăng nhập bị chặn (đang khoá)',
  login_blocked_disabled: 'Đăng nhập bị chặn (tài khoản khoá)', account_locked: 'Khoá tạm do nhập sai nhiều lần',
  logout: 'Đăng xuất', password_changed: 'Đổi mật khẩu', admin_created: 'Tạo admin', venue_created: 'Tạo quán',
  venue_updated: 'Cập nhật quán', owner_password_reset: 'Đặt lại mật khẩu chủ quán', user_status_changed: 'Đổi trạng thái tài khoản',
  staff_created: 'Tạo nhân viên', staff_updated: 'Cập nhật nhân viên', staff_password_reset: 'Đặt lại mật khẩu nhân viên',
  customer_created: 'Quầy tạo khách', customer_registered: 'Khách tự đăng ký', customer_status_changed: 'Khoá/mở khoá khách',
  customer_password_reset: 'Đặt lại mật khẩu khách', table_created: 'Thêm bàn', table_updated: 'Sửa bàn',
  product_created: 'Thêm món', product_updated: 'Sửa món', session_opened: 'Mở bàn', session_paid: 'Thanh toán phiên',
  session_voided: 'Huỷ phiên', session_start_changed: 'Chỉnh giờ bắt đầu', session_customer_set: 'Gắn khách vào phiên',
  item_added: 'Thêm món vào phiên', item_removed: 'Bỏ món khỏi phiên', booking_created: 'Khách đặt bàn',
  booking_cancelled: 'Khách huỷ lịch đặt', booking_cancelled_by_staff: 'Quầy huỷ lịch đặt', booking_checked_in: 'Nhận bàn từ lịch đặt',
  booking_no_show: 'Khách không đến', booking_settings_changed: 'Đổi luật đặt bàn/cọc', deposit_paid_mock: 'Trả cọc (mô phỏng)',
  checkin: 'Khách check-in', checkin_rejected: 'Check-in bị từ chối', game_settings_changed: 'Đổi cấu hình gamification',
  networks_changed: 'Đổi mạng wifi check-in', wheel_changed: 'Đổi vòng quay', wheel_spin: 'Khách quay thưởng', report_exported: 'Xuất báo cáo',
};

const ACTIONS = Object.entries(ACTION_LABEL).sort((a, b) => a[1].localeCompare(b[1], 'vi'));

interface Filters { action: string; venueId: string; q: string; from: string; to: string }
const EMPTY: Filters = { action: '', venueId: '', q: '', from: '', to: '' };

export function AdminAuditPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [debouncedQ, setDebouncedQ] = useState('');
  const venues = useLoad(() => api<Page<VenueSummary>>('/admin/venues?limit=200'), []);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(filters.q.trim()), 300);
    return () => clearTimeout(timer);
  }, [filters.q]);

  const params = new URLSearchParams({ limit: '200' });
  if (filters.action) params.set('action', filters.action);
  if (filters.venueId) params.set('venue_id', filters.venueId);
  if (debouncedQ) params.set('q', debouncedQ);
  if (filters.from) params.set('date_from', filters.from);
  if (filters.to) params.set('date_to', filters.to);
  const { data, error, loading, reload } = useLoad(() => api<AuditRow[]>(`/admin/audit?${params.toString()}`), [params.toString()]);

  const active = filters.action !== '' || filters.venueId !== '' || filters.q !== '' || filters.from !== '' || filters.to !== '';
  const set = (patch: Partial<Filters>) => setFilters(current => ({ ...current, ...patch }));
  const today = todayVN();

  return (
    <>
      <div className="page-head">
        <h1>Nhật ký hoạt động</h1>
        <Button onClick={reload} loading={loading && data !== null}>Tải lại</Button>
      </div>

      <form className="filter-bar" role="search" aria-label="Bộ lọc nhật ký" onSubmit={e => e.preventDefault()}>
        <Combobox label="Hành động" value={filters.action} onChange={action => set({ action })} emptyLabel="Tất cả hành động"
          options={ACTIONS.map(([value, label]) => ({ value, label }))} />
        <Combobox label="Quán" value={filters.venueId} onChange={venueId => set({ venueId })} emptyLabel="Tất cả quán"
          options={(venues.data?.items ?? []).map(v => ({ value: String(v.id), label: v.name, hint: v.slug }))} />
        <Field label="Tìm theo đối tượng hoặc người làm" placeholder="Ví dụ: bi-a-dai-nam, admin" value={filters.q} onChange={e => set({ q: e.target.value })} />
        <Field label="Từ ngày" type="date" max={filters.to || today} value={filters.from} onChange={e => set({ from: e.target.value })} />
        <Field label="Đến ngày" type="date" min={filters.from || undefined} max={today} value={filters.to} onChange={e => set({ to: e.target.value })} />
        <Button variant="ghost" disabled={!active} onClick={() => setFilters(EMPTY)}>Xoá bộ lọc</Button>
      </form>

      {error && !data ? <ErrorState message={error} onRetry={reload} />
        : !data ? <Skeleton height={240} />
        : (
          <>
            <p className="muted" role="status">{active ? `${data.length} kết quả khớp bộ lọc` : `${data.length} hoạt động gần nhất`}{data.length >= 200 ? ' (hiện tối đa 200, hãy thu hẹp bộ lọc)' : ''}</p>
            <DataTable rows={data} rowKey={r => String(r.id)}
              empty={active
                ? <EmptyState title="Không có hoạt động khớp" description="Thử bỏ bớt điều kiện hoặc mở rộng khoảng ngày." action={<Button onClick={() => setFilters(EMPTY)}>Xoá bộ lọc</Button>} />
                : <EmptyState title="Chưa có hoạt động" description="Đăng nhập, tạo quán và đổi trạng thái tài khoản sẽ được ghi tại đây." />}
              columns={[
                { key: 'at', header: 'Thời gian', render: r => dateTime(r.at) },
                { key: 'action', header: 'Hành động', render: r => ACTION_LABEL[r.action] ?? r.action },
                { key: 'venue', header: 'Quán', render: r => r.venue_name ?? '—' },
                { key: 'target', header: 'Đối tượng', render: r => r.target ?? '—' },
                { key: 'actor', header: 'Người thực hiện', render: r => r.actor_login ?? '—' },
              ]} />
          </>
        )}
    </>
  );
}
