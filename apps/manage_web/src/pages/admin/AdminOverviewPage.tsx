import { api } from '../../api';
import type { Overview } from '../../api';
import { useLoad } from '../../useLoad';
import { Card, ErrorState, Skeleton } from '../../ui/components';

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card flat>
      <div className="muted">{label}</div>
      <div className="num stat">{value}</div>
    </Card>
  );
}

export function AdminOverviewPage() {
  const { data, error, loading, reload } = useLoad(() => api<Overview>('/admin/overview'), []);
  return (
    <>
      <div className="page-head"><h1>Tổng quan hệ thống</h1></div>
      {loading && !data && <div className="grid-cards"><Skeleton height={96} /><Skeleton height={96} /><Skeleton height={96} /></div>}
      {error && <ErrorState message={error} onRetry={reload} />}
      {data && (
        <div className="grid-cards">
          <Stat label="Quán đang hoạt động" value={data.venues.active} />
          <Stat label="Quán tạm ngưng" value={data.venues.suspended} />
          <Stat label="Chủ quán" value={data.users.owner} />
          <Stat label="Nhân viên" value={data.users.staff} />
          <Stat label="Khách hàng" value={data.users.customer} />
        </div>
      )}
    </>
  );
}
