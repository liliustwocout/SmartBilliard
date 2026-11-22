import { api } from '../../api';
import type { MySession, Page } from '../../api';
import { useAuth } from '../../auth';
import { dateTime, money } from '../../format';
import { useLoad } from '../../useLoad';
import { Card, DataTable, EmptyState, ErrorState, Skeleton } from '../../ui/components';

export function MyHistoryPage() {
  const { state } = useAuth();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const { data, error, reload } = useLoad(() => api<Page<MySession>>(`/venues/${venueId}/my/sessions?limit=50`), [venueId]);
  return (
    <>
      <h1>Lịch sử chơi</h1>
      {error ? <Card><ErrorState message={error} onRetry={reload} /></Card>
        : !data ? <Skeleton height={160} />
        : (
          <DataTable rows={data.items} rowKey={s => s.id}
            empty={<EmptyState title="Chưa có lần chơi nào" description="Các phiên đã thanh toán, được quầy gắn với tài khoản của bạn, sẽ hiện ở đây." />}
            columns={[
              { key: 'table', header: 'Bàn', render: s => <strong>{s.table_name}</strong> },
              { key: 'time', header: 'Thời gian', render: s => dateTime(s.started_at) },
              { key: 'min', header: 'Phút', align: 'right', render: s => <span className="num">{s.billable_minutes ?? 0}</span> },
              { key: 'total', header: 'Tổng', align: 'right', render: s => <span className="num">{money(s.total ?? 0)}</span> },
            ]} />
        )}
    </>
  );
}
