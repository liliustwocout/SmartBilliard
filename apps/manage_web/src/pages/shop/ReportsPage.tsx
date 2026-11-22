import { useState } from 'react';
import { api } from '../../api';
import type { RevenueReport } from '../../api';
import { useAuth } from '../../auth';
import { addDays, money, todayVN } from '../../format';
import { useLoad } from '../../useLoad';
import { BarChart } from '../../ui/BarChart';
import { Button, Card, DataTable, EmptyState, ErrorState, Field, SelectField, Skeleton, Tabs } from '../../ui/components';

type Preset = 'today' | '7d' | '30d' | 'month' | 'custom';
type Group = 'day' | 'week' | 'month';

export function rangeFor(preset: Exclude<Preset, 'custom'>, today = todayVN()): { from: string; to: string } {
  if (preset === 'today') return { from: today, to: today };
  if (preset === '7d') return { from: addDays(today, -6), to: today };
  if (preset === '30d') return { from: addDays(today, -29), to: today };
  return { from: `${today.slice(0, 8)}01`, to: today };
}

/** Nhãn ngắn cho cột: ngày dd/MM, tuần "T dd/MM" (đầu tuần), tháng MM/yyyy. */
export function periodLabel(key: string, group: Group): string {
  if (group === 'month') return `${key.slice(5, 7)}/${key.slice(0, 4)}`;
  const label = `${key.slice(8, 10)}/${key.slice(5, 7)}`;
  return group === 'week' ? `T ${label}` : label;
}

const GROUP_TABS: Array<{ id: Group; label: string }> = [{ id: 'day', label: 'Theo ngày' }, { id: 'week', label: 'Theo tuần' }, { id: 'month', label: 'Theo tháng' }];
const PRESETS: Array<{ id: Preset; label: string }> = [{ id: 'today', label: 'Hôm nay' }, { id: '7d', label: '7 ngày' }, { id: '30d', label: '30 ngày' }, { id: 'month', label: 'Tháng này' }, { id: 'custom', label: 'Tuỳ chọn' }];

function Stat({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return <Card flat><div className="muted">{label}</div><div className="num stat" data-testid={testId} style={{ fontSize: 'var(--text-xl)' }}>{value}</div></Card>;
}

export function ReportsPage() {
  const { state } = useAuth();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const [preset, setPreset] = useState<Preset>('30d');
  const [range, setRange] = useState(() => rangeFor('30d'));
  const [group, setGroup] = useState<Group>('day');
  const [asTable, setAsTable] = useState(false);
  const query = `date_from=${range.from}&date_to=${range.to}`;
  const report = useLoad(() => api<RevenueReport>(`/venues/${venueId}/reports/revenue?${query}&group=${group}`), [venueId, range.from, range.to, group]);

  function choose(next: Preset) {
    setPreset(next);
    if (next !== 'custom') setRange(rangeFor(next));
  }

  const data = report.data;
  return (
    <>
      <div className="page-head">
        <h1>Báo cáo doanh thu</h1>
        <a className="btn btn-secondary" href={`/api/venues/${venueId}/reports/export.csv?${query}`} download>Xuất CSV hoá đơn</a>
      </div>

      <div className="stack">
        <Tabs label="Khoảng thời gian" value={preset} onChange={choose} tabs={PRESETS} />
        {preset === 'custom' && (
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <Field label="Từ ngày" type="date" value={range.from} max={range.to} onChange={e => e.target.value && setRange({ ...range, from: e.target.value })} />
            <Field label="Đến ngày" type="date" value={range.to} min={range.from} max={todayVN()} onChange={e => e.target.value && setRange({ ...range, to: e.target.value })} />
          </div>
        )}
      </div>

      {report.error && !data ? <Card><ErrorState message={report.error} onRetry={report.reload} /></Card>
        : !data ? <Skeleton height={300} />
        : data.totals.sessions === 0 ? (
          <Card><EmptyState title="Chưa có doanh thu trong khoảng này" description="Phiên đã thanh toán sẽ hiện ở đây. Thử chọn khoảng thời gian dài hơn." /></Card>
        ) : (
          <>
            <div className="grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 'var(--space-3)' }}>
              <Stat label="Doanh thu" value={money(data.totals.revenue)} testId="total-revenue" />
              <Stat label="Số phiên" value={String(data.totals.sessions)} testId="total-sessions" />
              <Stat label="Tiền giờ" value={money(data.totals.table_amount)} />
              <Stat label="Dịch vụ" value={money(data.totals.items_amount)} />
              <Stat label="Thu tiền mặt" value={money(data.totals.collected_cash)} />
              <Stat label="Thu chuyển khoản" value={money(data.totals.collected_transfer)} />
            </div>

            <div className="grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', alignItems: 'start' }}>
              <Card className="span-2">
                <div className="stack">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <h2>Doanh thu</h2>
                    <div className="row">
                      <Tabs label="Nhóm theo" value={group} onChange={setGroup} tabs={GROUP_TABS} />
                      <Button size="sm" variant="ghost" onClick={() => setAsTable(!asTable)}>{asTable ? 'Xem biểu đồ' : 'Xem dạng bảng'}</Button>
                    </div>
                  </div>
                  {asTable ? (
                    <DataTable rows={data.series} rowKey={r => r.key}
                      empty={<EmptyState title="Không có dữ liệu" description="" />}
                      columns={[{ key: 'k', header: 'Kỳ', render: r => periodLabel(r.key, group) },
                        { key: 's', header: 'Phiên', align: 'right', render: r => <span className="num">{r.sessions}</span> },
                        { key: 'r', header: 'Doanh thu', align: 'right', render: r => <span className="num">{money(r.revenue)}</span> }]} />
                  ) : (
                    <BarChart ariaLabel={`Doanh thu ${GROUP_TABS.find(t => t.id === group)?.label.toLowerCase()} từ ${data.from} đến ${data.to}`}
                      bars={data.series.map(r => ({ label: periodLabel(r.key, group), value: r.revenue, detail: `${r.sessions} phiên` }))} format={money} />
                  )}
                </div>
              </Card>
              <div className="stack">
                <h2>Theo bàn</h2>
                <DataTable rows={data.by_table} rowKey={r => String(r.table_id)} empty={<EmptyState title="Không có dữ liệu" description="" />}
                  columns={[{ key: 'n', header: 'Bàn', render: r => <strong>{r.table_name}</strong> },
                    { key: 's', header: 'Phiên', align: 'right', render: r => <span className="num">{r.sessions}</span> },
                    { key: 'm', header: 'Giờ chơi', align: 'right', render: r => <span className="num">{(r.minutes / 60).toFixed(1)}</span> },
                    { key: 'r', header: 'Doanh thu', align: 'right', render: r => <span className="num">{money(r.revenue)}</span> }]} />
              </div>
            </div>

            <h2 className="muted" style={{ fontSize: 'var(--text-lg)' }}>Chi tiết bổ sung</h2>
            <div className="grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', alignItems: 'start' }}>
              <div className="stack">
                <h2>Dịch vụ bán chạy</h2>
                <DataTable rows={data.top_items} rowKey={r => r.name} empty={<EmptyState title="Chưa bán dịch vụ nào" description="Món gọi thêm trong phiên sẽ hiện ở đây." />}
                  columns={[{ key: 'n', header: 'Món', render: r => r.name },
                    { key: 'q', header: 'SL', align: 'right', render: r => <span className="num">{r.quantity}</span> },
                    { key: 'a', header: 'Tiền', align: 'right', render: r => <span className="num">{money(r.amount)}</span> }]} />
              </div>
              <Card>
                <div className="stack">
                  <h2>Giờ khách vào chơi</h2>
                  <p className="muted">Số phiên bắt đầu theo từng giờ trong ngày (giờ Việt Nam).</p>
                  <BarChart ariaLabel="Số phiên theo giờ bắt đầu" format={n => `${n} phiên`} axisFormat={n => String(Math.round(n))}
                    bars={data.sessions_by_start_hour.map((n, h) => ({ label: `${h}h`, value: n }))} />
                </div>
              </Card>
            </div>
            <p className="muted">Doanh thu là tổng hoá đơn sau voucher ({money(data.totals.voucher_discount)} đã giảm), trước khi trừ tiền cọc đặt bàn ({money(data.totals.deposit_applied)}). Tiền thu tại quầy đã trừ cọc.</p>
          </>
        )}
    </>
  );
}
