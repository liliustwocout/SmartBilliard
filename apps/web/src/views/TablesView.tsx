import { activityLabel, dateTime, minuteSecond, money, sourceLabel, statusLabel, duration } from '../format';
import type { Session, Snapshot, Table } from '../types';

function TableDrawing({ active = false }: { active?: boolean }) {
  return (
    <div className={`billiard-table ${active ? 'playing' : ''}`} aria-hidden="true">
      <i className="pocket p1" /><i className="pocket p2" /><i className="pocket p3" />
      <i className="pocket p4" /><i className="pocket p5" /><i className="pocket p6" />
      <span className="table-line" /><span className="ball cue-ball" /><span className="ball yellow-ball" /><span className="ball red-ball" />
    </div>
  );
}

export type TablesViewProps = {
  data: Snapshot;
  expandedTableId: number | null;
  onToggleTable: (tableId: number) => void;
  locked: boolean;
  onOpenTable: (table: Table, backdateToAi?: boolean) => void;
  onShowCheckout: (session: Session) => void;
  onViewCamera: () => void;
};

export function TablesView({
  data,
  expandedTableId,
  onToggleTable,
  locked,
  onOpenTable,
  onShowCheckout,
  onViewCamera,
}: TablesViewProps) {
  const unbilledTables = data.tables.filter(item => item.unbilled_alert);
  const confirmTables = data.tables.filter(
    item => item.status === 'NEEDS_CONFIRMATION' && !item.session && !item.unbilled_alert,
  );
  const alertMinutes = Math.round((data.decision_config.unbilled_alert_seconds ?? 300) / 60);

  return (
    <div className="tables-view">
      {confirmTables.length > 0 && (
        <div className="alert-banner-confirm" role="alert">
          <div>
            <strong>AI PHÁT HIỆN ĐANG ĐÁNH — CHƯA MỞ BÀN</strong>
            <p>{confirmTables.map(item => item.name).join(' · ')} — xem camera để kiểm tra rồi xác nhận mở bàn.</p>
          </div>
          <div className="alert-banner-actions">
            {confirmTables.map(item => (
              <div key={item.id} className="alert-banner-item-actions">
                <button type="button" className="button subtle" onClick={onViewCamera}>Xem camera</button>
                <button type="button" className="button primary" disabled={locked} onClick={() => onOpenTable(item)}>
                  Xác nhận mở {item.name}
                </button>
                <button type="button" className="button subtle" disabled={locked} onClick={() => onOpenTable(item, true)}>
                  Tính bù giờ AI
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {unbilledTables.length > 0 && (
        <div className="alert-banner-5m" role="alert">
          <div>
            <strong>CẢNH BÁO QUÊN MỞ BÀN (&gt; {alertMinutes} PHÚT)</strong>
            <p>
              {unbilledTables
                .map(item => `${item.name} đang chơi ${minuteSecond(item.unbilled_playing_seconds ?? 0)} nhưng chưa mở giờ trên POS`)
                .join(' · ')}
            </p>
          </div>
          <div className="alert-banner-actions">
            {unbilledTables.map(item => (
              <div key={item.id} className="alert-banner-item-actions">
                <button type="button" className="button subtle" onClick={onViewCamera}>Xem camera</button>
                <button type="button" className="button primary" disabled={locked} onClick={() => onOpenTable(item)}>
                  Mở {item.name}
                </button>
                <button type="button" className="button subtle" disabled={locked} onClick={() => onOpenTable(item, true)}>
                  Tính bù giờ AI
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <section className="tables-section">
        <div className="section-heading">
          <div>
            <h2>Khu vực bàn chơi <span>{data.tables.length} bàn</span></h2>
            <p>Bấm vào thẻ bàn để mở rộng chi tiết phiên và quy tắc tính tiền.</p>
            <p className="open-mode-chip">
              {data.auto_open_enabled
                ? 'Chế độ: AI tự động mở bàn (thanh toán vẫn do nhân viên)'
                : 'Chế độ: Người duyệt (AI chỉ gợi ý)'}
            </p>
          </div>
          <span className="legend">
            <i className="dot green" />Đang chơi <i className="dot muted" />Chưa mở
          </span>
        </div>

        <div className="tables-grid">
          {data.tables.map(item => {
            const expanded = expandedTableId === item.id;
            const cardClasses = [
              'table-card',
              expanded ? 'selected expanded' : '',
              item.unbilled_alert ? 'alert-unbilled' : '',
            ].filter(Boolean).join(' ');

            return (
              <article key={item.id} className={cardClasses}>
                <button
                  type="button"
                  className="table-select"
                  onClick={() => onToggleTable(item.id)}
                  aria-label={`Xem ${item.name}`}
                  aria-expanded={expanded}
                >
                  <div className="table-card-heading">
                    <h3>{item.name}</h3>
                    <div className="table-badges">
                      {item.roi_calibrated === false || item.roi_enabled === false ? (
                        <span className="ai-pill uncalibrated">Chưa có vùng AI</span>
                      ) : (
                        <span className={`ai-pill ${(item.ai_activity ?? 'NOT_PLAYING').toLowerCase()}`}>
                          AI: {activityLabel[item.ai_activity ?? 'NOT_PLAYING'] ?? item.ai_activity}
                        </span>
                      )}
                      <span className={`status ${item.status.toLowerCase()}`}>{statusLabel[item.status] ?? item.status}</span>
                    </div>
                  </div>
                  {(item.roi_calibrated === false || item.roi_enabled === false) && (
                    <p className="ai-paused-note roi-missing-note">
                      Chưa có vùng AI · {item.roi_calibrated === false ? 'Chưa hiệu chuẩn ROI' : 'Đang tắt theo dõi ROI'}
                    </p>
                  )}
                  {item.ai_paused && <p className="ai-paused-note">AI tạm dừng · bàn đang có phiên</p>}
                  <TableDrawing active={!!item.session} />
                  <div className="table-amount">
                    <span>
                      {item.session
                        ? duration(item.session.elapsed_seconds)
                        : (item.unbilled_playing_seconds ?? 0) > 0
                          ? `Chơi chưa mở: ${minuteSecond(item.unbilled_playing_seconds ?? 0)} / ${minuteSecond(data.decision_config.unbilled_alert_seconds ?? 300)}`
                          : 'Chưa có phiên chơi'}
                    </span>
                    <strong>{item.session ? money(item.session.amount_vnd) : '—'}</strong>
                  </div>
                </button>

                {expanded && (
                  <div className="table-card-detail">
                    <div className="detail-grid">
                      <div>
                        <small>BẮT ĐẦU PHIÊN</small>
                        <strong>{dateTime(item.session?.started_at ?? null, data.timezone)}</strong>
                      </div>
                      <div>
                        <small>NGUỒN MỞ BÀN</small>
                        <strong>{item.session ? sourceLabel[item.session.trigger_source] ?? item.session.trigger_source : '—'}</strong>
                        {item.session?.evidence_source && (
                          <p>Bằng chứng: {sourceLabel[item.session.evidence_source] ?? 'mô phỏng'}</p>
                        )}
                      </div>
                      <div>
                        <small>QUY TẮC TÍNH TIỀN</small>
                        <strong>Làm tròn lên mỗi phút</strong>
                        <p>Đơn giá được chốt lúc mở bàn.</p>
                      </div>
                    </div>
                    <p className="detail-note">
                      {item.cooldown_remaining > 0
                        ? `Cooldown mô phỏng: còn ${item.cooldown_remaining}s. Nhân viên vẫn có thể mở bàn.`
                        : item.evidence_stale && !item.session
                          ? 'Tín hiệu đã cũ. Nhân viên cần kiểm tra bàn trước khi xác nhận.'
                          : 'Không tự đóng phiên khi người chơi rời vùng quan sát.'}
                    </p>
                  </div>
                )}

                <div className="table-card-footer">
                  <span>{money(item.hourly_rate)} / giờ</span>
                  {item.session ? (
                    <button
                      type="button"
                      className="button subtle"
                      disabled={locked}
                      onClick={() => onShowCheckout(item.session!)}
                    >
                      Thanh toán
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={`button ${item.unbilled_alert || item.status === 'NEEDS_CONFIRMATION' ? 'primary' : 'subtle'}`}
                      disabled={locked}
                      onClick={() => onOpenTable(item)}
                    >
                      {item.unbilled_alert
                        ? 'Mở bàn ngay!'
                        : item.status === 'NEEDS_CONFIRMATION'
                          ? 'Xác nhận mở'
                          : 'Mở bàn'}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
