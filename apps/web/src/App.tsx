import { useEffect, useRef, useState } from 'react';
import { request, useDashboard } from './api';
import { dateTime, duration, money, reasonLabel, sourceLabel, statusLabel } from './format';
import type { Observation, Session, Table } from './types';

function TableDrawing({ active = false }: { active?: boolean }) {
  return <div className={`billiard-table ${active ? 'playing' : ''}`} aria-hidden="true">
    <i className="pocket p1" /><i className="pocket p2" /><i className="pocket p3" />
    <i className="pocket p4" /><i className="pocket p5" /><i className="pocket p6" />
    <span className="table-line" /><span className="ball cue-ball" /><span className="ball yellow-ball" /><span className="ball red-ball" />
  </div>;
}

export default function App() {
  const { snapshot: data, online } = useDashboard();
  const [tab, setTab] = useState('dashboard');
  const [selected, setSelected] = useState(1);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [simTable, setSimTable] = useState(1);
  const [simulating, setSimulating] = useState(false);
  const [ambiguous, setAmbiguous] = useState(false);
  const [confidence, setConfidence] = useState(.9);
  const [history, setHistory] = useState<Session[]>([]);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [quote, setQuote] = useState<Session | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const lastEvent = useRef<Observation | null>(null);
  const actionInFlight = useRef(false);
  const table = data?.tables.find(item => item.id === selected);
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
      const payload: Observation = { event_id: crypto.randomUUID(), table_id: simTable,
        present: true, confidence, ambiguous };
      lastEvent.current = payload;
      try {
        await request('/simulations/observations', payload);
        if (!cancelled) timer = setTimeout(tick, 900);
      } catch (reason) {
        if (!cancelled) { setSimulating(false); setError((reason as Error).message); }
      }
    }
    void tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [simulating, simTable, ambiguous, confidence, online]);

  useEffect(() => {
    if (quote) dialog.current?.showModal();
    else dialog.current?.close();
  }, [quote]);

  async function act(work: () => Promise<unknown>, message = '') {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true); setError(''); setNotice('');
    try { await work(); if (message) setNotice(message); }
    catch (reason) { setError((reason as Error).message); }
    finally { actionInFlight.current = false; setBusy(false); }
  }

  function openTable(target: Table) {
    void act(() => request(`/tables/${target.id}/open`, {}), `Đã mở ${target.name.toLowerCase()} bằng thao tác nhân viên.`);
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
    const payload: Observation = { event_id: crypto.randomUUID(), table_id: simTable,
      present: false, confidence: 0, ambiguous: false };
    lastEvent.current = payload;
    await act(() => request('/simulations/observations', payload), 'Đã dừng mô phỏng. Phiên đang chơi vẫn được giữ nguyên.');
  }

  const locked = busy || !online;
  return <div className="app-shell">
    <aside className="sidebar">
      <a href="#" className="brand" onClick={() => setTab('dashboard')} aria-label="SmartBilliard về tổng quan">
        <span className="brand-mark">8</span><span>smart<span className="brand-light">billiard</span><small>CLUB OPERATIONS</small></span>
      </a>
      <div className="workspace"><span className="workspace-avatar">SB</span><div>Phòng demo PSI2026<small>Không gian cục bộ</small></div></div>
      <p className="nav-label">QUẢN LÝ VẬN HÀNH</p>
      <nav aria-label="Điều hướng chính">
        {[['dashboard', '◫', 'Tổng quan bàn'], ['history', '≡', 'Lịch sử phiên'], ['system', '⚙', 'Hệ thống & camera']].map(([id, icon, label]) =>
          <button key={id} className={tab === id ? 'nav-item current' : 'nav-item'} onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}>
            <span aria-hidden="true">{icon}</span>{label}{id === 'dashboard' && <b>{data?.tables.length ?? '—'}</b>}
          </button>)}
      </nav>
      <div className="sidebar-bottom"><span className="tiny-label">PHIÊN BẢN THỬ NGHIỆM</span><strong>Vận hành minh bạch.</strong><p>Mỗi phiên chơi, mỗi tín hiệu đều có nguồn rõ ràng.</p><div className="phase-tag">PSI 2026 <span>Phase 02</span></div></div>
      <div className="operator"><span className="workspace-avatar">NV</span><div>Nhân viên demo<small>Chỉ truy cập máy này</small></div></div>
    </aside>
    <main>
      <header className="topbar"><div><span className="breadcrumb">Không gian làm việc</span><span className="breadcrumb-divider">/</span><span>Phòng demo</span></div><div className="connection"><i className={online ? 'dot green' : 'dot amber'} />{online ? 'Đã đồng bộ' : 'Đang kết nối lại'}<span className="local-tag">LOCAL</span></div></header>
      <div className="page-content">
        <div className="page-heading"><div><p className="eyebrow">SMARTBILLIARD / {tab === 'history' ? 'LỊCH SỬ' : tab === 'system' ? 'HỆ THỐNG' : 'TỔNG QUAN'}</p><h1>{tab === 'history' ? 'Lịch sử phiên chơi' : tab === 'system' ? 'Cấu hình & khả năng' : 'Mọi bàn chơi. Một góc nhìn.'}</h1><p>{tab === 'dashboard' ? 'Theo dõi hoạt động, xác nhận mở bàn và quản lý phiên chơi tại một nơi.' : 'Dữ liệu cục bộ, nguồn tín hiệu rõ ràng, trạng thái được cập nhật từ backend.'}</p></div><div className="server-clock"><small>GIỜ MÁY CHỦ</small><span>{data ? dateTime(data.server_time, data.timezone) : 'Đang tải…'}</span></div></div>
        <div className="demo-banner"><span className="demo-badge">{data?.mode === 'MANUAL_ONLY' ? 'THỦ CÔNG' : 'MÔ PHỎNG'}</span><p>{data?.mode === 'MANUAL_ONLY' ? 'Nguồn mô phỏng đã tắt. Bạn vẫn có thể mở và chốt bàn bằng tay.' : 'Đang kiểm chứng luồng tích hợp bằng sự kiện nhân tạo. Camera và nhận diện AI chưa được triển khai.'}</p></div>
        {!online && <div className="message warning" role="status">Mất kết nối realtime. Dữ liệu có thể đã cũ; các thao tác đang tạm khóa.</div>}
        {error && <div className="message error" role="alert">{error}<button onClick={() => setError('')} aria-label="Đóng lỗi">×</button></div>}
        {notice && <div className="message success" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Đóng thông báo">×</button></div>}
        {!data ? <section className="empty-state"><h2>Đang kết nối backend</h2><p>Khởi động API tại 127.0.0.1:8000 để tải dữ liệu. Không có số liệu demo được điền sẵn.</p></section> : <>
          <section className="stats-grid" aria-label="Thống kê từ máy chủ">
            <div className="stat"><span>Bàn đang hoạt động</span><strong>{data.active_count}<small>/ {data.tables.length}</small></strong><p><i className="dot green" />{data.tables.length - data.active_count} bàn chưa có phiên</p></div>
            <div className="stat"><span>Tiền phiên đang chơi</span><strong>{money(data.running_amount_vnd)}</strong><p>Tạm tính bởi backend · làm tròn phút</p></div>
            <div className="stat"><span>Doanh thu demo đã chốt</span><strong>{money(data.revenue_vnd)}</strong><p>Tổng hóa đơn đã lưu trên máy này</p></div>
            <div className="stat"><span>Chờ nhân viên xác nhận</span><strong className="text-amber">{data.tables.filter(item => item.status === 'NEEDS_CONFIRMATION').length.toString().padStart(2, '0')}</strong><p>{data.auto_open_enabled ? 'Tự mở mô phỏng đã bật' : 'Tự động mở bàn đang tắt'}</p></div>
          </section>
          {tab === 'dashboard' && <div className="dashboard-columns"><section className="tables-section">
            <div className="section-heading"><div><h2>Khu vực bàn chơi <span>{data.tables.length} bàn</span></h2><p>Chọn một bàn để xem phiên và tín hiệu.</p></div><span className="legend"><i className="dot green" />Đang chơi <i className="dot muted" />Chưa mở</span></div>
            <div className="tables-grid">{data.tables.map(item => <article key={item.id} className={`table-card ${selected === item.id ? 'selected' : ''}`}>
              <button className="table-select" onClick={() => setSelected(item.id)} aria-label={`Xem ${item.name}`} aria-pressed={selected === item.id}>
                <div className="table-card-heading"><h3>{item.name}</h3><span className={`status ${item.status.toLowerCase()}`}>{statusLabel[item.status] ?? item.status}</span></div>
                <TableDrawing active={!!item.session} />
                <div className="table-amount"><span>{item.session ? duration(item.session.elapsed_seconds) : 'Chưa có phiên chơi'}</span><strong>{item.session ? money(item.session.amount_vnd) : '—'}</strong></div>
              </button>
              <div className="table-card-footer"><span>{money(item.hourly_rate)} / giờ</span>{item.session ? <button className="button subtle" disabled={locked} onClick={() => void showCheckout(item.session!)}>Thanh toán</button> : <button className={`button ${item.status === 'NEEDS_CONFIRMATION' ? 'primary' : 'subtle'}`} disabled={locked} onClick={() => openTable(item)}>{item.status === 'NEEDS_CONFIRMATION' ? 'Xác nhận mở' : 'Mở bàn'}</button>}</div>
            </article>)}</div>
            {table && <section className="detail-panel"><div className="section-heading"><h2>Chi tiết · {table.name}</h2><span className={`status ${table.status.toLowerCase()}`}>{statusLabel[table.status]}</span></div><div className="detail-grid"><div><small>BẮT ĐẦU PHIÊN</small><strong>{dateTime(table.session?.started_at ?? null, data.timezone)}</strong></div><div><small>NGUỒN MỞ BÀN</small><strong>{table.session ? sourceLabel[table.session.trigger_source] ?? table.session.trigger_source : '—'}</strong>{table.session?.evidence_source && <p>Bằng chứng: mô phỏng</p>}</div><div><small>QUY TẮC TÍNH TIỀN</small><strong>Làm tròn lên mỗi phút</strong><p>Đơn giá được chốt lúc mở bàn.</p></div></div><p className="detail-note">{table.cooldown_remaining > 0 ? `Cooldown mô phỏng: còn ${table.cooldown_remaining}s. Nhân viên vẫn có thể mở bàn.` : table.evidence_stale && !table.session ? 'Tín hiệu đã cũ. Nhân viên cần kiểm tra bàn trước khi xác nhận.' : 'Không tự đóng phiên khi người chơi rời vùng quan sát.'}</p></section>}
          </section><aside className="activity-column">
            <section className="simulation-panel"><div className="section-heading"><h2>Bộ phát mô phỏng</h2><span className="outline-badge">TEST</span></div><p>Gửi tín hiệu mỗi ~1 giây. Đồng hồ máy chủ quyết định khi đủ {data.decision_config.presence_seconds} giây.</p>
              <label htmlFor="simulation-table">Bàn nhận tín hiệu</label><select id="simulation-table" value={simTable} disabled={simulating} onChange={event => setSimTable(Number(event.target.value))}>{data.tables.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
              <label htmlFor="confidence">Confidence đầu vào <b>{confidence.toFixed(2)}</b></label><input id="confidence" type="range" min="0" max="1" step="0.05" value={confidence} disabled={simulating} onChange={event => setConfidence(Number(event.target.value))} />
              <label className="checkbox-label"><input type="checkbox" checked={ambiguous} disabled={simulating} onChange={event => setAmbiguous(event.target.checked)} />Vị trí không rõ bàn (AMBIGUOUS)</label>
              <button className={`button full-width ${simulating ? 'danger' : 'primary'}`} disabled={locked || !data.simulation_enabled} onClick={() => simulating ? void stopSimulation() : setSimulating(true)}>{simulating ? 'Dừng phát tín hiệu' : 'Bắt đầu tín hiệu hiện diện'}</button>
              <button className="button subtle full-width" disabled={locked || simulating || !lastEvent.current || !data.simulation_enabled} onClick={() => void act(() => request('/simulations/observations', lastEvent.current), 'Đã gửi lại event_id cũ. Backend loại trùng, không tạo thêm phiên.')}>Gửi lại sự kiện gần nhất</button>
              <div className="simulation-state"><i className={simulating && online ? 'dot green' : 'dot muted'} />{simulating ? online ? 'Đang phát tín hiệu nhân tạo' : 'Tạm dừng vì mất kết nối' : 'Chưa phát tín hiệu'}<span>{data.decision_config.policy}</span></div>
            </section>
            <section className="activity-panel"><div className="section-heading"><h2>Nhật ký tín hiệu</h2><span className="outline-badge">{table?.name}</span></div><div className="event-list">{data.events.filter(item => item.table_id === selected).slice(0, 8).map(item => <div className="event" key={item.id}><i className="event-dot" /><div><strong>{reasonLabel[item.reason] ?? item.reason}</strong><p>MÔ PHỎNG · {item.event_type} · {item.confidence.toFixed(2)}</p><time dateTime={item.timestamp}>{dateTime(item.timestamp, data.timezone)}</time></div></div>)}{!data.events.some(item => item.table_id === selected) && <div className="empty-inline">Chưa có tín hiệu cho bàn này.<br />Dùng bộ phát mô phỏng để bắt đầu.</div>}</div><p className="footnote">Hiển thị tối đa 8 tín hiệu của bàn trong 30 sự kiện gần nhất. Không lưu hình ảnh cá nhân.</p></section>
          </aside></div>}
          {tab === 'history' && <section className="history-panel"><div className="section-heading"><h2>Phiên đã ghi nhận</h2><span className="outline-badge">25 phiên / trang</span></div>{historyLoading ? <p role="status">Đang tải lịch sử…</p> : <div className="history-scroll"><table><thead><tr><th>Bàn</th><th>Bắt đầu / kết thúc</th><th>Nguồn mở</th><th>Số phút tính phí</th><th>Tiền đã chốt</th><th>Trạng thái</th></tr></thead><tbody>{history.map(item => <tr key={item.id}><td><strong>Bàn {item.table_id.toString().padStart(2, '0')}</strong><small>{item.id.slice(0, 8)}</small></td><td>{dateTime(item.started_at, data.timezone)}<small>{dateTime(item.ended_at, data.timezone)}</small></td><td>{sourceLabel[item.trigger_source] ?? item.trigger_source}{item.evidence_source && <small>Bằng chứng mô phỏng</small>}</td><td>{item.ended_at ? item.billable_minutes : 'Đang chơi'}</td><td>{item.total_amount === null ? 'Chưa chốt' : money(item.total_amount)}</td><td><span className={`status ${item.status === 'ACTIVE' ? 'active' : 'closed'}`}>{item.status === 'ACTIVE' ? 'Đang chơi' : 'Đã thanh toán demo'}</span></td></tr>)}</tbody></table>{history.length === 0 && <p className="empty-inline">Chưa có phiên nào. Mở bàn trong trang Tổng quan để bắt đầu.</p>}</div>}<div className="pagination"><button className="button subtle" disabled={!historyPage || historyLoading} onClick={() => setHistoryPage(value => value - 1)}>Trang trước</button><span>Trang {historyPage + 1}</span><button className="button subtle" disabled={history.length < 25 || historyLoading} onClick={() => setHistoryPage(value => value + 1)}>Trang sau</button></div></section>}
          {tab === 'system' && <section className="system-panel"><div className="section-heading"><h2>Trạng thái triển khai Phase 2</h2><span className="outline-badge">OFFLINE READY</span></div><dl className="system-grid"><div><dt>Nguồn dữ liệu</dt><dd>{data.mode === 'SIMULATED' ? 'Sự kiện mô phỏng / nhân viên' : 'Nhân viên'}</dd></div><div><dt>Camera / tracking / ROI</dt><dd>Chưa triển khai · Phase 3</dd></div><div><dt>Nhận diện gậy</dt><dd>Chưa có model được kiểm chứng</dd></div><div><dt>Chính sách</dt><dd>{data.decision_config.policy}</dd></div><div><dt>Tự mở bàn demo</dt><dd>{data.auto_open_enabled ? 'Đã bật' : 'Đã tắt · yêu cầu nhân viên'}</dd></div><div><dt>Thời gian hiện diện</dt><dd>{data.decision_config.presence_seconds} giây</dd></div><div><dt>Confidence vào / giữ</dt><dd>{data.decision_config.confidence_enter} / {data.decision_config.confidence_exit}</dd></div><div><dt>Khoảng cách tín hiệu tối đa</dt><dd>{data.decision_config.max_observation_gap_seconds} giây</dd></div><div><dt>Khoảng vắng được làm mượt</dt><dd>{data.decision_config.absence_grace_seconds} giây</dd></div><div><dt>Cooldown sau chốt</dt><dd>{data.decision_config.cooldown_seconds} giây</dd></div><div><dt>Múi giờ hiển thị</dt><dd>{data.timezone}</dd></div><div><dt>Lưu trữ & đồng bộ</dt><dd>SQLite cục bộ · WebSocket</dd></div></dl><div className="message warning">Chỉnh ngưỡng tại configs/decision.toml, biến môi trường tại .env rồi khởi động lại API. Camera, vẽ polygon và hai chế độ REAL_CLUB / MINI_TABLE nằm ngoài Phase 2.</div></section>}
        </>}
        <footer className="page-footer"><span>SmartBilliard <b>·</b> PSI2026</span><span>Phiên & tiền được xác định bởi máy chủ · Hóa đơn demo, không tích hợp thanh toán</span></footer>
      </div>
    </main>
    <dialog ref={dialog} onCancel={event => { if (checkoutBusy) event.preventDefault(); else setQuote(null); }} onClose={() => { if (!checkoutBusy) setQuote(null); }}><div className="checkout-dialog"><p className="eyebrow">CHỐT HÓA ĐƠN DEMO</p><h2>Thanh toán bàn {quote?.table_id.toString().padStart(2, '0')}</h2><p>Tạm tính chính thức từ backend tại thời điểm mở hộp thoại.</p><strong className="checkout-amount">{money(quote?.amount_vnd ?? 0)}</strong><dl><div><dt>Thời gian chơi</dt><dd>{duration(quote?.elapsed_seconds ?? 0)}</dd></div><div><dt>Phút tính phí</dt><dd>{quote?.billable_minutes} phút</dd></div><div><dt>Đơn giá đã chốt</dt><dd>{money(quote?.hourly_rate_snapshot ?? 0)} / giờ</dd></div></dl><p className="footnote">Số tiền được tính lại khi xác nhận; có thể tăng nếu sang phút kế tiếp. Thao tác chốt phiên và lưu hóa đơn cục bộ.</p><div className="dialog-actions"><button className="button subtle" disabled={checkoutBusy} onClick={() => setQuote(null)}>Quay lại</button><button className="button primary" disabled={locked || checkoutBusy} onClick={() => void checkout()}>{checkoutBusy ? 'Đang chốt…' : 'Xác nhận thanh toán'}</button></div></div></dialog>
  </div>;
}
