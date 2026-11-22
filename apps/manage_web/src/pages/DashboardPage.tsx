import { useEffect, useState } from 'react';
import { fetchHealth } from '../api';
import { Badge, Button, Card, EmptyState, Skeleton } from '../ui/components';

type Status = 'loading' | 'ok' | 'error';

export function DashboardPage() {
  const [status, setStatus] = useState<Status>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then(() => { if (!cancelled) setStatus('ok'); })
      .catch(reason => { if (!cancelled) { setStatus('error'); setMessage((reason as Error).message); } });
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>Tổng quan bàn</h1>
        <div role="status" data-status={status}>
          {status === 'loading' && <Skeleton width={150} height={26} />}
          {status === 'ok' && <Badge tone="ok">Máy chủ sẵn sàng</Badge>}
          {status === 'error' && <Badge tone="danger">{`Mất kết nối: ${message}`}</Badge>}
        </div>
      </div>
      <Card>
        <EmptyState title="Quán chưa có bàn nào"
          description="Thêm bàn đầu tiên để bắt đầu mở bàn và tính giờ. Tính năng này sẽ có ở bản tới."
          action={<Button variant="primary" disabled>Thêm bàn</Button>} />
      </Card>
    </>
  );
}
