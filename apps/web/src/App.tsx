import { useEffect, useRef, useState } from 'react';
import { request, useDashboard } from './api';
import { RoiEditor } from './RoiEditor';
import { duration, money } from './format';
import { HistoryView } from './views/HistoryView';
import { LabView } from './views/LabView';
import { LiveView } from './views/LiveView';
import { SystemView } from './views/SystemView';
import { TablesView } from './views/TablesView';
import type { ActivityState, Observation, Session, Table } from './types';

type TabId = 'dashboard' | 'live' | 'lab' | 'history' | 'calibration' | 'system';

const NAV_ITEMS: Array<{ id: TabId; icon: string; label: string }> = [
  { id: 'dashboard', icon: '◫', label: 'Tổng quan bàn' },
  { id: 'live', icon: '◉', label: 'Camera trực tiếp' },
  { id: 'lab', icon: '◈', label: 'Thử nghiệm' },
  { id: 'history', icon: '≡', label: 'Lịch sử phiên' },
  { id: 'calibration', icon: '⛶', label: 'Hiệu chuẩn ROI' },
  { id: 'system', icon: '⚙', label: 'Hệ thống & camera' },
];

function getModeLabel(mode?: string): string {
  if (mode === 'CAMERA_LIVE') return 'CAMERA LIVE';
  if (mode === 'VIDEO_LIVE') return 'VIDEO LIVE';
  if (mode === 'MANUAL_ONLY') return 'THỦ CÔNG';
  return 'MÔ PHỎNG';
}

export default function App() {
  const { snapshot: data, online } = useDashboard();
  const [tab, setTab] = useState<TabId>('dashboard');
  const [expandedTableId, setExpandedTableId] = useState<number | null>(null);
  const [logTableId, setLogTableId] = useState(1);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [simTable, setSimTable] = useState(1);
  const [simulating, setSimulating] = useState(false);
  const [ambiguous, setAmbiguous] = useState(false);
  const [confidence, setConfidence] = useState(0.9);
  const [activityState, setActivityState] = useState<ActivityState>('PLAYING');
  const [history, setHistory] = useState<Session[]>([]);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [quote, setQuote] = useState<Session | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const lastEvent = useRef<Observation | null>(null);
  const actionInFlight = useRef(false);
  const recentSessionChange = data?.tables.map(item => item.session?.id ?? '-').join(',');

  useEffect(() => {
    if (tab !== 'history') return;
    let cancelled = false;
    setHistoryLoading(true);
    request<Session[]>(`/sessions?limit=25&offset=${historyPage * 25}`)
      .then(items => { if (!cancelled) setHistory(items); })
      .catch(reason => { if (!cancelled) setError(String(reason.message)); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [tab, historyPage, recentSessionChange, online]);

  useEffect(() => {
    if (!simulating || !online) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      const payload: Observation = {
        event_id: crypto.randomUUID(),
        table_id: simTable,
        present: true,
        confidence,
        ambiguous,
        activity_state: activityState,
      };
      lastEvent.current = payload;
      try {
        await request('/simulations/observations', payload);
        if (!cancelled) timer = setTimeout(tick, 900);
      } catch (reason) {
        if (!cancelled) {
          setSimulating(false);
          setError((reason as Error).message);
        }
      }
    }
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [simulating, simTable, ambiguous, confidence, activityState, online]);

  useEffect(() => {
    if (quote) dialog.current?.showModal();
    else dialog.current?.close();
  }, [quote]);

  async function act(work: () => Promise<unknown>, message = '') {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
      if (message) setNotice(message);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  function openTable(target: Table, backdateToAi = false) {
    const query = backdateToAi ? '?backdate_to_ai=true' : '';
    const msg = backdateToAi
      ? `Đã mở ${target.name.toLowerCase()} và tính giờ từ lúc AI phát hiện chơi.`
      : `Đã mở ${target.name.toLowerCase()} bằng thao tác nhân viên.`;
    void act(() => request(`/tables/${target.id}/open${query}`, {}), msg);
  }

  async function showCheckout(session: Session) {
    await act(async () => setQuote(await request<Session>(`/sessions/${session.id}/quote`)));
  }

  async function checkout() {
    if (!quote || checkoutBusy) return;
    setCheckoutBusy(true);
    await act(async () => {
      const paid = await request<Session>(`/sessions/${quote.id}/checkout`, {});
      setQuote(null);
      setNotice(`Đã chốt bàn ${paid.table_id}: ${money(paid.total_amount ?? 0)}. Hóa đơn demo đã lưu.`);
    });
    setCheckoutBusy(false);
  }

  async function stopSimulation() {
    setSimulating(false);
    const payload: Observation = {
      event_id: crypto.randomUUID(),
      table_id: simTable,
      present: false,
      confidence: 0,
      ambiguous: false,
    };
    lastEvent.current = payload;
    await act(
      () => request('/simulations/observations', payload),
      'Đã dừng mô phỏng. Phiên đang chơi vẫn được giữ nguyên.',
    );
  }

  function handleChildNotice(msg: string) {
    if (msg) {
      setError('');
      setNotice(msg);
    }
  }

  function handleChildError(msg: string) {
    if (msg) {
      setNotice('');
      setError(msg);
    } else {
      setError('');
    }
  }

  function startCamera() {
    void act(() => request('/camera/start', {}), 'Đã bật camera nhận diện trực tiếp.');
  }

  function stopCamera() {
    void act(() => request('/camera/stop', {}), 'Đã dừng luồng camera.');
  }

  const locked = busy || !online;
  const modeClass = `mode-${(data?.mode ?? 'SIMULATED').toLowerCase()}`;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#dashboard"
          className="brand"
          onClick={event => { event.preventDefault(); setTab('dashboard'); }}
          aria-label="SmartBilliard về tổng quan"
        >
          <span className="brand-mark">8</span>
          <span>smart<span className="brand-light">billiard</span><small>CLUB OPERATIONS</small></span>
        </a>
        <div className="workspace">
          <span className="workspace-avatar">SB</span>
          <div>Phòng demo PSI2026<small>Không gian cục bộ</small></div>
        </div>
        <p className="nav-label">QUẢN LÝ VẬN HÀNH</p>
        <nav aria-label="Điều hướng chính">
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? 'nav-item current' : 'nav-item'}
              onClick={() => setTab(item.id)}
              aria-current={tab === item.id ? 'page' : undefined}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
              {item.id === 'dashboard' && <b>{data?.tables.length ?? '—'}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="tiny-label">PHIÊN BẢN THỬ NGHIỆM</span>
          <strong>Vận hành minh bạch.</strong>
          <p>Mỗi phiên chơi, mỗi tín hiệu đều có nguồn rõ ràng.</p>
          <div className="phase-tag">PSI 2026 <span>Phase 02</span></div>
        </div>
        <div className="operator">
          <span className="workspace-avatar">NV</span>
          <div>Nhân viên demo<small>Chỉ truy cập máy này</small></div>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="breadcrumb">Không gian làm việc</span>
            <span className="breadcrumb-divider">/</span>
            <span>Phòng demo</span>
          </div>
          <div className="topbar-right">
            <span className={`mode-badge ${modeClass}`} title={simulating ? 'Bộ phát mô phỏng đang hoạt động' : 'Chế độ nguồn hiện tại'}>
              {simulating && <i className="dot green" aria-hidden="true" />}
              {getModeLabel(data?.mode)}
            </span>
            <div className="connection">
              <i className={online ? 'dot green' : 'dot amber'} />
              {online ? 'Đã đồng bộ' : 'Đang kết nối lại'}
              <span className="local-tag">LOCAL</span>
            </div>
          </div>
        </header>

        <div className="page-content">
          {!online && (
            <div className="message warning" role="status">
              Mất kết nối realtime. Dữ liệu có thể đã cũ; các thao tác đang tạm khóa.
            </div>
          )}
          {error && (
            <div className="message error" role="alert">
              {error}
              <button type="button" onClick={() => setError('')} aria-label="Đóng lỗi">×</button>
            </div>
          )}
          {notice && (
            <div className="message success" role="status">
              {notice}
              <button type="button" onClick={() => setNotice('')} aria-label="Đóng thông báo">×</button>
            </div>
          )}

          {!data ? (
            <section className="empty-state">
              <h2>Đang kết nối backend</h2>
              <p>Khởi động API tại 127.0.0.1:8000 để tải dữ liệu. Không có số liệu demo được điền sẵn.</p>
            </section>
          ) : (
            <>
              <div style={{ display: tab === 'dashboard' ? 'block' : 'none' }}>
                <TablesView
                  data={data}
                  expandedTableId={expandedTableId}
                  onToggleTable={id => setExpandedTableId(prev => (prev === id ? null : id))}
                  locked={locked}
                  onOpenTable={openTable}
                  onShowCheckout={session => void showCheckout(session)}
                  onViewCamera={() => setTab('live')}
                />
              </div>

              <div style={{ display: tab === 'live' ? 'block' : 'none' }}>
                <LiveView
                  data={data}
                  active={tab === 'live'}
                  locked={locked}
                  onStartCamera={startCamera}
                  onStopCamera={stopCamera}
                  onJumpCalibration={() => setTab('calibration')}
                  onNotice={handleChildNotice}
                  onError={handleChildError}
                />
              </div>

              <div style={{ display: tab === 'lab' ? 'block' : 'none' }}>
                <LabView
                  data={data}
                  online={online}
                  locked={locked}
                  simTable={simTable}
                  onChangeSimTable={setSimTable}
                  simulating={simulating}
                  onStartSimulation={() => setSimulating(true)}
                  onStopSimulation={() => void stopSimulation()}
                  onReplayLastEvent={() => void act(
                    () => request('/simulations/observations', lastEvent.current),
                    'Đã gửi lại event_id cũ. Backend loại trùng, không tạo thêm phiên.',
                  )}
                  hasLastEvent={!!lastEvent.current}
                  ambiguous={ambiguous}
                  onChangeAmbiguous={setAmbiguous}
                  confidence={confidence}
                  onChangeConfidence={setConfidence}
                  activityState={activityState}
                  onChangeActivityState={setActivityState}
                  logTableId={logTableId}
                  onChangeLogTableId={setLogTableId}
                  onStartCamera={startCamera}
                  onStopCamera={stopCamera}
                  onOpenLiveTab={() => setTab('live')}
                  onJumpCalibration={() => setTab('calibration')}
                  onNotice={handleChildNotice}
                  onError={handleChildError}
                />
              </div>

              <div style={{ display: tab === 'history' ? 'block' : 'none' }}>
                <HistoryView
                  data={data}
                  history={history}
                  historyPage={historyPage}
                  historyLoading={historyLoading}
                  onChangePage={setHistoryPage}
                />
              </div>

              <div style={{ display: tab === 'calibration' ? 'block' : 'none' }}>
                <RoiEditor
                  tableCount={data.tables.length}
                  active={tab === 'calibration'}
                  sourceKey={`${data.camera_source ?? ''}|${data.mode}|${data.camera_ready ? '1' : '0'}`}
                  onSaved={() => setNotice('Cấu hình ROI đã được lưu và cập nhật.')}
                />
              </div>

              <div style={{ display: tab === 'system' ? 'block' : 'none' }}>
                <SystemView
                  data={data}
                  locked={locked}
                  onNotice={msg => { setError(''); setNotice(msg); }}
                  onError={msg => { setNotice(''); setError(msg); }}
                />
              </div>
            </>
          )}

          <footer className="page-footer">
            <span>SmartBilliard <b>·</b> PSI2026</span>
            <span>Phiên &amp; tiền được xác định bởi máy chủ · Hóa đơn demo, không tích hợp thanh toán</span>
          </footer>
        </div>
      </main>

      <dialog
        ref={dialog}
        onCancel={event => { if (checkoutBusy) event.preventDefault(); else setQuote(null); }}
        onClose={() => { if (!checkoutBusy) setQuote(null); }}
      >
        <div className="checkout-dialog">
          <p className="eyebrow">CHỐT HÓA ĐƠN DEMO</p>
          <h2>Thanh toán bàn {quote?.table_id.toString().padStart(2, '0')}</h2>
          <p>Tạm tính chính thức từ backend tại thời điểm mở hộp thoại.</p>
          <strong className="checkout-amount">{money(quote?.amount_vnd ?? 0)}</strong>
          <dl>
            <div><dt>Thời gian chơi</dt><dd>{duration(quote?.elapsed_seconds ?? 0)}</dd></div>
            <div><dt>Phút tính phí</dt><dd>{quote?.billable_minutes} phút</dd></div>
            <div><dt>Đơn giá đã chốt</dt><dd>{money(quote?.hourly_rate_snapshot ?? 0)} / giờ</dd></div>
          </dl>
          <p className="footnote">
            Số tiền được tính lại khi xác nhận; có thể tăng nếu sang phút kế tiếp. Thao tác chốt phiên và lưu hóa đơn cục bộ.
          </p>
          <div className="dialog-actions">
            <button type="button" className="button subtle" disabled={checkoutBusy} onClick={() => setQuote(null)}>
              Quay lại
            </button>
            <button type="button" className="button primary" disabled={locked || checkoutBusy} onClick={() => void checkout()}>
              {checkoutBusy ? 'Đang chốt…' : 'Xác nhận thanh toán'}
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
