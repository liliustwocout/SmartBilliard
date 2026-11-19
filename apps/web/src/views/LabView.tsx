import { VideoAutomationPanel } from '../VideoAutomationPanel';
import { dateTime, reasonLabel, sourceLabel } from '../format';
import type { ActivityState, Snapshot } from '../types';

export type LabViewProps = {
  data: Snapshot;
  online: boolean;
  locked: boolean;
  simTable: number;
  onChangeSimTable: (id: number) => void;
  simulating: boolean;
  onStartSimulation: () => void;
  onStopSimulation: () => void;
  onReplayLastEvent: () => void;
  hasLastEvent: boolean;
  ambiguous: boolean;
  onChangeAmbiguous: (val: boolean) => void;
  confidence: number;
  onChangeConfidence: (val: number) => void;
  activityState: ActivityState;
  onChangeActivityState: (val: ActivityState) => void;
  logTableId: number;
  onChangeLogTableId: (id: number) => void;
  onStartCamera: () => void;
  onStopCamera: () => void;
  onOpenLiveTab: () => void;
  onJumpCalibration: () => void;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

function getModeBadge(mode: string): string {
  if (mode === 'CAMERA_LIVE') return 'CAMERA LIVE';
  if (mode === 'VIDEO_LIVE') return 'VIDEO LIVE';
  if (mode === 'MANUAL_ONLY') return 'THỦ CÔNG';
  return 'MÔ PHỎNG';
}

function getBannerDescription(data: Snapshot): string {
  if (data.mode === 'CAMERA_LIVE' || data.mode === 'VIDEO_LIVE') {
    return data.model_status.person.loaded
      ? 'Nguồn hình đã kết nối; model người đã nạp. Tab Thử nghiệm dùng để chạy video kiểm thử, tạo dữ liệu mẫu hoặc đối chiếu tín hiệu.'
      : 'Nguồn hình đã kết nối nhưng chưa nạp model người. Khung hình và ROI vẫn hiển thị, chưa có nhận diện AI.';
  }
  if (data.mode === 'MANUAL_ONLY') {
    return 'Nguồn mô phỏng đã tắt. Bạn vẫn có thể mở và chốt bàn bằng tay ở tab Tổng quan bàn.';
  }
  return 'Đang kiểm chứng luồng tích hợp bằng dữ liệu sự kiện mô phỏng nhân tạo (không phải camera AI). Dùng tab Hiệu chuẩn ROI để cấu hình camera.';
}

export function LabView({
  data,
  online,
  locked,
  simTable,
  onChangeSimTable,
  simulating,
  onStartSimulation,
  onStopSimulation,
  onReplayLastEvent,
  hasLastEvent,
  ambiguous,
  onChangeAmbiguous,
  confidence,
  onChangeConfidence,
  activityState,
  onChangeActivityState,
  logTableId,
  onChangeLogTableId,
  onStartCamera,
  onStopCamera,
  onOpenLiveTab,
  onJumpCalibration,
  onNotice,
  onError,
}: LabViewProps) {
  const tableEvents = data.events.filter(item => item.table_id === logTableId).slice(0, 8);

  return (
    <div className="lab-view">
      <div className="demo-banner">
        <span className="demo-badge">{getModeBadge(data.mode)}</span>
        <p>{getBannerDescription(data)}</p>
      </div>

      <div className="lab-grid">
        <section className="simulation-panel">
          <div className="section-heading">
            <h2>Bộ phát mô phỏng</h2>
            <span className="outline-badge">DỮ LIỆU NHÂN TẠO</span>
          </div>
          <p>
            Gửi tín hiệu giả lập nhân tạo mỗi ~1 giây (không phải camera AI). Đồng hồ máy chủ quyết định khi đủ {data.decision_config.presence_seconds} giây.
          </p>

          <label htmlFor="simulation-table">Bàn nhận tín hiệu</label>
          <select
            id="simulation-table"
            value={simTable}
            disabled={simulating}
            onChange={event => onChangeSimTable(Number(event.target.value))}
          >
            {data.tables.map(item => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>

          <label htmlFor="activity-state">Hành vi giả lập</label>
          <select
            id="activity-state"
            value={activityState}
            disabled={simulating}
            onChange={event => onChangeActivityState(event.target.value as ActivityState)}
          >
            <option value="PLAYING">PLAYING — Đang ngắm / đánh bi-a</option>
            <option value="NOT_PLAYING">NOT_PLAYING — Đứng xem / lau bàn</option>
            <option value="UNKNOWN">UNKNOWN — Chưa rõ / bị che khuất</option>
          </select>

          <label htmlFor="confidence">
            Confidence đầu vào <b>{confidence.toFixed(2)}</b>
          </label>
          <input
            id="confidence"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={confidence}
            disabled={simulating}
            onChange={event => onChangeConfidence(Number(event.target.value))}
          />

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={ambiguous}
              disabled={simulating}
              onChange={event => onChangeAmbiguous(event.target.checked)}
            />
            Vị trí không rõ bàn (AMBIGUOUS)
          </label>

          <div className="lab-camera-box">
            <div className="camera-toggle-grid">
              <button type="button" className="button subtle" disabled={locked} onClick={onStartCamera}>
                Bật Camera
              </button>
              <button type="button" className="button subtle" disabled={locked} onClick={onStopCamera}>
                Dừng Camera
              </button>
            </div>
            <div className="camera-mini-preview">
              <img
                src="/api/camera/stream"
                alt="Xem nhanh luồng camera"
                className="camera-mini-img"
                onClick={onOpenLiveTab}
                title="Nhấn để phóng to luồng camera"
              />
              <button type="button" className="camera-expand-btn" onClick={onOpenLiveTab}>
                Phóng to ⛶
              </button>
            </div>
          </div>

          <button
            type="button"
            className={`button full-width ${simulating ? 'danger' : 'primary'}`}
            disabled={locked || !data.simulation_enabled}
            onClick={() => (simulating ? onStopSimulation() : onStartSimulation())}
          >
            {simulating ? 'Dừng phát tín hiệu' : 'Bắt đầu tín hiệu hiện diện'}
          </button>

          <button
            type="button"
            className="button subtle full-width"
            disabled={locked || simulating || !hasLastEvent || !data.simulation_enabled}
            onClick={onReplayLastEvent}
          >
            Gửi lại sự kiện gần nhất
          </button>

          <div className="simulation-state">
            <i className={simulating && online ? 'dot green' : 'dot muted'} />
            {simulating ? (online ? 'Đang phát tín hiệu nhân tạo' : 'Tạm dừng vì mất kết nối') : 'Chưa phát tín hiệu'}
            <span>{data.decision_config.policy}</span>
          </div>
        </section>

        <div className="lab-side-column">
          <VideoAutomationPanel
            compact
            onJumpCalibration={onJumpCalibration}
            onNotice={onNotice}
            onError={onError}
          />

          <section className="activity-panel">
            <div className="section-heading">
              <h2>Nhật ký tín hiệu</h2>
              <select
                className="log-table-select"
                aria-label="Chọn bàn xem nhật ký"
                value={logTableId}
                onChange={event => onChangeLogTableId(Number(event.target.value))}
              >
                {data.tables.map(item => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </div>
            <div className="event-list">
              {tableEvents.map(item => (
                <div className="event" key={item.id}>
                  <i className="event-dot" />
                  <div>
                    <strong>{reasonLabel[item.reason] ?? item.reason}</strong>
                    <p>{sourceLabel[item.source] ?? item.source} · {item.event_type} · {item.confidence.toFixed(2)}</p>
                    <time dateTime={item.timestamp}>{dateTime(item.timestamp, data.timezone)}</time>
                  </div>
                </div>
              ))}
              {tableEvents.length === 0 && (
                <div className="empty-inline">
                  Chưa có tín hiệu cho bàn này.<br />
                  Dùng camera hoặc bộ phát mô phỏng nhân tạo để bắt đầu.
                </div>
              )}
            </div>
            <p className="footnote">
              Hiển thị tối đa 8 tín hiệu của bàn trong 30 sự kiện gần nhất. Không lưu hình ảnh cá nhân.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
