import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { CheckinMode, GameSettingsData, GameStats, OwnerPrize, PrizeKind } from '../../api';
import { useAuth } from '../../auth';
import { dateTime } from '../../format';
import { useLoad } from '../../useLoad';
import { Badge, Button, Card, ErrorState, Field, SelectField, Skeleton, Tabs, useToast } from '../../ui/components';

type Tab = 'checkin' | 'wheel' | 'streak' | 'today';

const MODE_LABEL: Record<CheckinMode, string> = {
  off: 'Tắt check-in', wifi: 'Chỉ cần wifi của quán', code: 'Chỉ cần mã tại quầy', wifi_or_code: 'Wifi hoặc mã tại quầy', wifi_and_code: 'Cả wifi và mã tại quầy',
};
const KIND_LABEL: Record<PrizeKind, string> = { points: 'Điểm', discount_vnd: 'Giảm giá (₫)', free_minutes: 'Miễn phí (phút)', nothing: 'Chúc may mắn' };

interface PrizeDraft { id?: number; name: string; kind: PrizeKind; value: string; percent: string; stock: string; days: string }

const SAMPLE: PrizeDraft[] = [
  { name: '+20 điểm', kind: 'points', value: '20', percent: '40', stock: '', days: '30' },
  { name: '+50 điểm', kind: 'points', value: '50', percent: '15', stock: '', days: '30' },
  { name: 'Giảm 10.000 ₫', kind: 'discount_vnd', value: '10000', percent: '12', stock: '20', days: '30' },
  { name: 'Miễn phí 30 phút', kind: 'free_minutes', value: '30', percent: '3', stock: '3', days: '30' },
  { name: 'Chúc may mắn', kind: 'nothing', value: '0', percent: '30', stock: '', days: '30' },
];

const toDraft = (p: OwnerPrize): PrizeDraft => ({ id: p.id, name: p.name, kind: p.kind, value: String(p.value), percent: String(p.percent), stock: p.stock === null ? '' : String(p.stock), days: String(p.voucher_valid_days) });

/** Tổng tỷ lệ tính bằng điểm cơ bản (1% = 100) để tránh sai số số thực. */
export const toBp = (percent: string): number => Math.round(Number(percent) * 100);
export const totalBp = (rows: PrizeDraft[]): number => rows.reduce((sum, r) => sum + (Number.isFinite(toBp(r.percent)) ? toBp(r.percent) : 0), 0);

function CheckinTab({ venueId, draft, setDraft }: { venueId: number; draft: GameSettingsData; setDraft: (value: GameSettingsData) => void }) {
  const toast = useToast();
  const networks = useLoad(() => api<{ networks: Array<{ cidr: string; label: string | null }>; your_ip: string }>(`/venues/${venueId}/networks`), [venueId]);
  const [list, setList] = useState<Array<{ cidr: string; label: string }>>([]);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false); // chỉ cho thao tác sau khi danh sách đã nạp xong, tránh bị ghi đè
  useEffect(() => { if (networks.data) { setList(networks.data.networks.map(n => ({ cidr: n.cidr, label: n.label ?? '' }))); setReady(true); } }, [networks.data]);

  async function saveNetworks() {
    setError('');
    try {
      await api(`/venues/${venueId}/networks`, { method: 'PUT', body: { networks: list.filter(n => n.cidr.trim()).map(n => ({ cidr: n.cidr, label: n.label || null })) } });
      toast('success', 'Đã lưu mạng của quán.');
      networks.reload();
    } catch (failure) { setError((failure as Error).message); }
  }

  return (
    <div className="stack">
      <Card><div className="stack">
        <h2>Cách khách check-in</h2>
        <SelectField label="Chế độ" value={draft.checkin_mode} onChange={e => setDraft({ ...draft, checkin_mode: e.target.value as CheckinMode })}>
          {(Object.keys(MODE_LABEL) as CheckinMode[]).map(m => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
        </SelectField>
        <Field label="Điểm mỗi lần check-in" inputMode="numeric" value={String(draft.checkin_points)} onChange={e => setDraft({ ...draft, checkin_points: Number(e.target.value) || 0 })} />
        <Field label="Mã tại quầy đổi sau (giây)" inputMode="numeric" value={String(draft.code_rotation_seconds)} onChange={e => setDraft({ ...draft, code_rotation_seconds: Number(e.target.value) || 0 })}
          hint="Mã hiện ở trang Mã check-in. Mã kỳ trước vẫn dùng được thêm một kỳ." />
      </div></Card>
      <Card><div className="stack">
        <h2>Mạng wifi của quán</h2>
        <p className="muted">Trình duyệt không đọc được tên wifi, nên quán khai báo địa chỉ IP công cộng của mạng quán. Khách chỉ check-in được khi đang dùng đúng mạng này. Khách dùng VPN hoặc chung đường truyền với nơi khác có thể bị nhầm: hãy kết hợp mã tại quầy nếu cần chặt hơn.</p>
        {ready && networks.data && <p>IP bạn đang dùng: <strong className="num">{networks.data.your_ip}</strong> {!list.some(n => n.cidr === networks.data!.your_ip) &&
          <Button size="sm" onClick={() => setList([...list, { cidr: networks.data!.your_ip, label: 'Mạng hiện tại' }])}>Thêm IP này</Button>}</p>}
        {list.map((n, i) => (
          <div key={i} className="row" style={{ alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 180px' }}><Field label="IP hoặc dải IP" value={n.cidr} onChange={e => setList(list.map((x, j) => j === i ? { ...x, cidr: e.target.value } : x))} placeholder="203.0.113.0/24" /></div>
            <div style={{ flex: '1 1 140px' }}><Field label="Ghi chú" value={n.label} onChange={e => setList(list.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} /></div>
            <Button variant="ghost" aria-label="Xoá mạng này" onClick={() => setList(list.filter((_, j) => j !== i))}>✕</Button>
          </div>
        ))}
        {!ready && !networks.error && <Skeleton height={60} />}
        {ready && list.length === 0 && <p className="muted">Chưa khai báo mạng nào.</p>}
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row"><Button onClick={() => setList([...list, { cidr: '', label: '' }])} disabled={!ready || list.length >= 10}>Thêm mạng</Button><Button variant="primary" disabled={!ready} onClick={() => void saveNetworks()}>Lưu mạng</Button></div>
      </div></Card>
    </div>
  );
}

function WheelTab({ venueId, draft, setDraft }: { venueId: number; draft: GameSettingsData; setDraft: (value: GameSettingsData) => void }) {
  const toast = useToast();
  const wheel = useLoad(() => api<{ prizes: OwnerPrize[]; total_bp: number }>(`/venues/${venueId}/wheel`), [venueId]);
  const [rows, setRows] = useState<PrizeDraft[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (wheel.data) setRows(wheel.data.prizes.map(toDraft)); }, [wheel.data]);

  const total = totalBp(rows);
  const update = (i: number, patch: Partial<PrizeDraft>) => setRows(rows.map((r, j) => j === i ? { ...r, ...patch } : r));

  async function save() {
    setError('');
    const prizes = rows.map(r => ({ id: r.id ?? null, name: r.name, kind: r.kind, value: r.kind === 'nothing' ? 0 : Number(r.value), weight_bp: toBp(r.percent),
      stock: r.kind === 'nothing' || r.stock.trim() === '' ? null : Number(r.stock), voucher_valid_days: Number(r.days) || 30 }));
    if (prizes.some(p => !p.name.trim() || !Number.isFinite(p.value) || !Number.isFinite(p.weight_bp) || p.weight_bp < 0)) { setError('Kiểm tra lại tên, giá trị và tỷ lệ của các ô.'); return; }
    if (total !== 10000) { setError(`Tổng tỷ lệ phải đúng 100% (hiện ${total / 100}%).`); return; }
    setBusy(true);
    try {
      await api(`/venues/${venueId}/wheel`, { method: 'PUT', body: { prizes } });
      toast('success', 'Đã lưu vòng quay. Tỷ lệ mới áp dụng cho các lượt quay sau.');
      wheel.reload();
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  async function saveGuarantee() {
    try {
      await api(`/venues/${venueId}/game-settings`, { method: 'PUT', body: draft });
      toast('success', 'Đã lưu cài đặt thưởng mỗi ngày.');
    } catch (failure) { toast('error', (failure as Error).message); }
  }

  return (
    <div className="stack">
      <Card><div className="stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2>Các ô trên vòng quay</h2>
          <Badge tone={total === 10000 ? 'ok' : 'danger'}>Tổng {total / 100}%</Badge>
        </div>
        {wheel.error && <ErrorState message={wheel.error} onRetry={wheel.reload} />}
        {!wheel.data && !wheel.error && <Skeleton height={140} />}
        {rows.map((r, i) => (
          <div key={r.id ?? `new-${i}`} className="prize-row">
            <Field label="Tên ô" value={r.name} onChange={e => update(i, { name: e.target.value })} />
            <SelectField label="Loại" value={r.kind} onChange={e => update(i, { kind: e.target.value as PrizeKind })}>
              {(Object.keys(KIND_LABEL) as PrizeKind[]).map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
            </SelectField>
            <Field label="Giá trị" inputMode="numeric" disabled={r.kind === 'nothing'} value={r.kind === 'nothing' ? '' : r.value} onChange={e => update(i, { value: e.target.value })} />
            <Field label="Tỷ lệ (%)" inputMode="decimal" value={r.percent} onChange={e => update(i, { percent: e.target.value })} />
            <Field label="Còn lại" inputMode="numeric" disabled={r.kind === 'nothing'} value={r.stock} onChange={e => update(i, { stock: e.target.value })} placeholder="Không giới hạn" />
            <Button variant="ghost" aria-label={`Xoá ô ${r.name}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</Button>
          </div>
        ))}
        <p className="muted">Tỷ lệ này được hiển thị công khai cho khách. Voucher dùng được {rows[0]?.days ?? 30} ngày kể từ lúc trúng. Phải có ít nhất một ô "Chúc may mắn".</p>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row">
          <Button onClick={() => setRows([...rows, { name: '', kind: 'points', value: '10', percent: '0', stock: '', days: '30' }])} disabled={!wheel.data || rows.length >= 12}>Thêm ô</Button>
          <Button variant="ghost" disabled={!wheel.data} onClick={() => setRows(SAMPLE)}>Điền cấu hình mẫu</Button>
          <Button variant="primary" loading={busy} disabled={!wheel.data} onClick={() => void save()}>Lưu vòng quay</Button>
        </div>
      </div></Card>

      <Card><div className="stack">
        <h2>Thưởng đảm bảo mỗi ngày</h2>
        <p className="muted">Mỗi ngày hệ thống tự chọn ngẫu nhiên vài lượt quay "trúng chắc chắn" trong số lượt dự kiến. Khách không biết lượt nào. Nếu hôm đó có ít lượt quay hơn số thưởng tối thiểu thì không thể đảm bảo.</p>
        <label className="row"><input type="checkbox" checked={draft.wheel_enabled} onChange={e => setDraft({ ...draft, wheel_enabled: e.target.checked })} /> Bật vòng quay</label>
        <div className="grid-cards" style={{ alignItems: 'start' }}>
          <SelectField label="Thưởng tối thiểu mỗi ngày" value={draft.min_daily_prizes} onChange={e => setDraft({ ...draft, min_daily_prizes: Number(e.target.value) })}>
            <option value={0}>0 (không đảm bảo)</option><option value={1}>1</option><option value={2}>2</option>
          </SelectField>
          <Field label="Thưởng tối đa mỗi ngày" inputMode="numeric" value={String(draft.max_daily_prizes)} onChange={e => setDraft({ ...draft, max_daily_prizes: Number(e.target.value) || 0 })} hint="Ngân sách chặn trên." />
          <Field label="Số lượt quay dự kiến mỗi ngày" inputMode="numeric" value={String(draft.expected_daily_checkins)} onChange={e => setDraft({ ...draft, expected_daily_checkins: Number(e.target.value) || 0 })} hint="Các lượt trúng chắc chắn nằm trong số này." />
          <Field label="Lượt quay dùng được trong (ngày)" inputMode="numeric" value={String(draft.spin_expiry_days)} onChange={e => setDraft({ ...draft, spin_expiry_days: Number(e.target.value) || 0 })} />
        </div>
        <div><Button variant="primary" onClick={() => void saveGuarantee()}>Lưu cài đặt thưởng</Button></div>
      </div></Card>
    </div>
  );
}

function StreakTab({ draft, setDraft }: { draft: GameSettingsData; setDraft: (value: GameSettingsData) => void }) {
  const rows = draft.streak_milestones;
  const set = (next: typeof rows) => setDraft({ ...draft, streak_milestones: next });
  return (
    <Card><div className="stack">
      <h2>Thưởng theo chuỗi ngày check-in</h2>
      <p className="muted">Khách check-in liên tiếp đủ số ngày sẽ nhận thêm điểm thưởng. Bỏ lỡ một ngày thì chuỗi tính lại từ đầu.</p>
      {rows.map((m, i) => (
        <div key={i} className="row" style={{ alignItems: 'flex-end' }}>
          <Field label="Số ngày liên tiếp" inputMode="numeric" value={String(m.days)} onChange={e => set(rows.map((x, j) => j === i ? { ...x, days: Number(e.target.value) || 0 } : x))} />
          <Field label="Điểm thưởng" inputMode="numeric" value={String(m.bonus)} onChange={e => set(rows.map((x, j) => j === i ? { ...x, bonus: Number(e.target.value) || 0 } : x))} />
          <Button variant="ghost" aria-label="Xoá mốc" onClick={() => set(rows.filter((_, j) => j !== i))}>✕</Button>
        </div>
      ))}
      <div><Button onClick={() => set([...rows, { days: 5, bonus: 30 }])} disabled={rows.length >= 8}>Thêm mốc</Button></div>
    </div></Card>
  );
}

function TodayTab({ venueId }: { venueId: number }) {
  const stats = useLoad(() => api<GameStats>(`/venues/${venueId}/game-stats`), [venueId]);
  if (stats.error) return <ErrorState message={stats.error} onRetry={stats.reload} />;
  if (!stats.data) return <Skeleton height={160} />;
  const s = stats.data;
  const short = s.plan.guaranteed_total > s.plan.guaranteed_given && s.plan.spins >= s.plan.expected;
  return (
    <div className="stack">
      <div className="grid-cards">
        <Card flat><div className="muted">Check-in hôm nay</div><div className="num stat">{s.checkins_today}</div></Card>
        <Card flat><div className="muted">Lượt quay hôm nay</div><div className="num stat">{s.plan.spins}</div></Card>
        <Card flat><div className="muted">Phần thưởng đã phát</div><div className="num stat">{s.plan.prizes_given}<span className="muted" style={{ fontSize: 'var(--text-lg)' }}> / tối đa {s.plan.max_prizes}</span></div></Card>
        <Card flat><div className="muted">Thưởng đảm bảo</div><div className="num stat" data-testid="guarantee">{s.plan.guaranteed_given}<span className="muted" style={{ fontSize: 'var(--text-lg)' }}> / {s.plan.guaranteed_total}</span></div></Card>
      </div>
      {short && <p className="notice" role="alert">Chưa phát đủ thưởng đảm bảo dù đã quá số lượt dự kiến: có thể các phần thưởng thật đã hết hàng.</p>}
      {!s.plan.created && <p className="muted">Kế hoạch thưởng của hôm nay sẽ được tạo khi có lượt quay đầu tiên.</p>}
      <h2>Lượt quay gần đây</h2>
      {s.recent.length === 0 ? <p className="muted">Chưa có lượt quay nào.</p> : (
        <ul className="item-list">{s.recent.map((r, i) => <li key={i}><span>{r.customer}</span><span>{r.prize}</span><span className="muted">{dateTime(r.at)}</span></li>)}</ul>
      )}
    </div>
  );
}

export function GamePage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const settings = useLoad(() => api<GameSettingsData>(`/venues/${venueId}/game-settings`), [venueId]);
  const [draft, setDraft] = useState<GameSettingsData | null>(null);
  const [tab, setTab] = useState<Tab>('checkin');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (settings.data) setDraft(settings.data); }, [settings.data]);

  async function save() {
    if (!draft) return;
    setBusy(true);
    try {
      await api(`/venues/${venueId}/game-settings`, { method: 'PUT', body: draft });
      toast('success', 'Đã lưu cài đặt.');
      settings.reload();
    } catch (failure) { toast('error', (failure as Error).message); } finally { setBusy(false); }
  }

  if (settings.error && !draft) return <Card><ErrorState message={settings.error} onRetry={settings.reload} /></Card>;
  if (!draft) return <Skeleton height={240} />;
  return (
    <>
      <div className="page-head">
        <h1>Gamification</h1>
        {tab !== 'today' && tab !== 'wheel' && <Button variant="primary" loading={busy} onClick={() => void save()}>Lưu cài đặt</Button>}
      </div>
      <p className="muted">Phần thưởng chỉ là điểm và voucher dùng tại quán, không quy đổi thành tiền. Hãy kiểm tra quy định về khuyến mại, quay thưởng trước khi chạy thật.</p>
      <Tabs label="Phần gamification" value={tab} onChange={setTab} tabs={[
        { id: 'checkin', label: 'Check-in' }, { id: 'wheel', label: 'Vòng quay' }, { id: 'streak', label: 'Chuỗi ngày' }, { id: 'today', label: 'Hôm nay' }]} />
      {tab === 'checkin' && <CheckinTab venueId={venueId} draft={draft} setDraft={setDraft} />}
      {tab === 'wheel' && <WheelTab venueId={venueId} draft={draft} setDraft={setDraft} />}
      {tab === 'streak' && <StreakTab draft={draft} setDraft={setDraft} />}
      {tab === 'today' && <TodayTab venueId={venueId} />}
    </>
  );
}
