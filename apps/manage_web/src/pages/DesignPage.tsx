import { useState } from 'react';
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, SelectField, Skeleton, TableCard, Tabs, useToast } from '../ui/components';

interface SampleRow { id: string; name: string; status: string; amount: string }
// Dữ liệu minh hoạ giao diện: KHÔNG phải số liệu thật của quán nào.
const SAMPLE: SampleRow[] = [
  { id: 'a', name: 'Mẫu A', status: 'Đã thanh toán', amount: '120.000 ₫' },
  { id: 'b', name: 'Mẫu B', status: 'Đang chơi', amount: '85.000 ₫' },
];

export function DesignPage() {
  const toast = useToast();
  const [tab, setTab] = useState<'one' | 'two'>('one');
  const [confirm, setConfirm] = useState(false);

  return (
    <>
      <div className="page-head">
        <h1>Giao diện mẫu</h1>
        <Badge tone="info">Dữ liệu minh hoạ, không phải số liệu thật</Badge>
      </div>

      <Card><div className="stack">
        <h2>Nút</h2>
        <div className="row">
          <Button variant="primary">Mở bàn</Button>
          <Button>Xem lịch sử</Button>
          <Button variant="ghost">Bỏ qua</Button>
          <Button variant="danger" onClick={() => setConfirm(true)}>Huỷ phiên</Button>
          <Button variant="primary" loading>Đang lưu</Button>
          <Button disabled>Không khả dụng</Button>
        </div>
      </div></Card>

      <Card><div className="stack">
        <h2>Thẻ bàn</h2>
        <div className="grid-cards">
          <TableCard name="Bàn mẫu 1" state="free" rate="60.000 ₫/giờ" actions={<Button variant="primary" size="sm">Mở bàn</Button>} />
          <TableCard name="Bàn mẫu 2" state="playing" clock="01:24:08" amount="85.000 ₫" rate="60.000 ₫/giờ" actions={<Button size="sm">Tính tiền</Button>} />
          <TableCard name="Bàn mẫu 3" state="reserved" rate="60.000 ₫/giờ" actions={<Button size="sm">Nhận bàn</Button>} />
        </div>
      </div></Card>

      <Card><div className="stack">
        <h2>Biểu mẫu</h2>
        <div className="grid-cards">
          <Field label="Tên bàn" placeholder="Ví dụ: Bàn VIP" hint="Hiển thị trên màn hình quầy." />
          <Field label="Số điện thoại" defaultValue="09" error="Số điện thoại cần đủ 10 chữ số." />
          <SelectField label="Loại bàn"><option>Pool</option><option>Carom</option></SelectField>
        </div>
      </div></Card>

      <Card><div className="stack">
        <h2>Tab và bảng</h2>
        <Tabs label="Ví dụ tab" value={tab} onChange={setTab} tabs={[{ id: 'one', label: 'Hôm nay' }, { id: 'two', label: 'Tuần này' }]} />
        <DataTable rows={SAMPLE} rowKey={r => r.id} empty={<EmptyState title="Chưa có phiên" description="Phiên chơi sẽ hiện ở đây." />}
          columns={[
            { key: 'n', header: 'Bàn', render: r => r.name },
            { key: 's', header: 'Trạng thái', render: r => <Badge tone={r.status === 'Đang chơi' ? 'warn' : 'ok'}>{r.status}</Badge> },
            { key: 'a', header: 'Tiền', align: 'right', render: r => <span className="num">{r.amount}</span> },
          ]} />
      </div></Card>

      <Card><div className="stack">
        <h2>Trạng thái: đang tải, trống, lỗi, thành công</h2>
        <div className="row"><Skeleton width={180} height={20} /><Skeleton width={120} height={20} /></div>
        <ErrorState message="Không tải được danh sách bàn. Kiểm tra kết nối rồi thử lại." onRetry={() => toast('info', 'Đang thử lại…')} />
        <div className="row">
          <Button onClick={() => toast('success', 'Đã lưu bảng giá.')}>Hiện thông báo thành công</Button>
          <Button onClick={() => toast('error', 'Không lưu được. Thử lại sau ít phút.')}>Hiện thông báo lỗi</Button>
        </div>
      </div></Card>

      <ConfirmDialog open={confirm} danger title="Huỷ phiên chơi này?" confirmLabel="Huỷ phiên"
        description="Phiên sẽ bị huỷ và không tính tiền. Thao tác này không hoàn tác được."
        onCancel={() => setConfirm(false)} onConfirm={() => { setConfirm(false); toast('success', 'Đã huỷ phiên.'); }} />
    </>
  );
}
