import { Card, EmptyState } from '../ui/components';

export function CustomerHomePage() {
  return (
    <>
      <div className="page-head"><h1>Xin chào</h1></div>
      <Card><EmptyState title="Khu vực dành cho khách đang được xây dựng"
        description="Check-in, vòng quay may mắn và đặt bàn sẽ có trong các bản tới." /></Card>
    </>
  );
}
