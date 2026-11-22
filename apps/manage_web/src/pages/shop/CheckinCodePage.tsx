import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { CheckinCode } from '../../api';
import { useAuth } from '../../auth';
import { useLoad } from '../../useLoad';
import { Card, ErrorState, Skeleton } from '../../ui/components';

/** Mã check-in đổi liên tục để khách nhập khi check-in (chống check-in từ xa). Hiện trên màn hình quầy. */
export function CheckinCodePage() {
  const { state } = useAuth();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const code = useLoad(() => api<CheckinCode>(`/venues/${venueId}/checkin-code`), [venueId]);
  const [left, setLeft] = useState(0);

  useEffect(() => { if (code.data) setLeft(code.data.expires_in_seconds); }, [code.data]);
  useEffect(() => {
    const timer = setInterval(() => {
      setLeft(value => {
        if (value <= 1) { code.reload(); return 0; }
        return value - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [code.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  if (code.error && !code.data) return <Card><ErrorState message={code.error} onRetry={code.reload} /></Card>;
  if (!code.data) return <Skeleton height={200} />;
  const mm = String(Math.floor(left / 60)).padStart(2, '0');
  const ss = String(left % 60).padStart(2, '0');
  return (
    <>
      <div className="page-head"><h1>Mã check-in</h1></div>
      {!code.data.enabled ? (
        <Card><p className="muted">Quán đang dùng chế độ check-in không cần mã. Chủ quán có thể bật mã trong phần Gamification.</p></Card>
      ) : (
        <Card className="code-card">
          <p className="muted">Khách nhập mã này trong mục Quà tặng để check-in</p>
          <p className="num checkin-code" data-testid="checkin-code" aria-live="off">{code.data.code}</p>
          <p className="muted">Đổi mã sau <span className="num">{mm}:{ss}</span></p>
        </Card>
      )}
    </>
  );
}
