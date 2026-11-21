import { VideoAutomationPanel } from '../VideoAutomationPanel';
import type { Snapshot } from '../types';

export type LiveViewProps = {
  data: Snapshot;
  locked: boolean;
  onStartCamera: () => void;
  onStopCamera: () => void;
  onJumpCalibration: () => void;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function LiveView({
  data,
  locked,
  onStartCamera,
  onStopCamera,
  onJumpCalibration,
  onNotice,
  onError,
}: LiveViewProps) {
  const uncalibratedTables = data.tables.filter(
    item => item.roi_calibrated === false || item.roi_enabled === false,
  );

  return (
    <div className="live-view">
      {uncalibratedTables.length > 0 && (
        <div className="alert-banner-confirm live-roi-alert" role="status">
          <div>
            <strong>CHƯA CÓ VÙNG AI CHO {uncalibratedTables.length} BÀN</strong>
            <p>
              {uncalibratedTables
                .map(item => `${item.name} (${item.roi_calibrated === false ? 'chưa hiệu chuẩn ROI' : 'đang tắt theo dõi'})`)
                .join(' · ')}{' '}
              — chưa nhận tín hiệu AI từ camera.
            </p>
          </div>
          <button type="button" className="button primary" onClick={onJumpCalibration}>
            Hiệu chuẩn ROI ⛶
          </button>
        </div>
      )}
      <section className="live-camera-panel">
      <div className="live-main-column">
        <div className="live-stream-frame">
          <img
            src="/api/camera/stream"
            alt="Luồng Camera AI Trực tiếp"
            className="live-stream-img"
          />
        </div>

        <div className="live-card">
          <p className="live-legend-title">CHÚ GIẢI TRỰC QUAN</p>
          <ul className="live-legend-list">
            <li><strong className="legend-green">Khung xanh lá + Xương:</strong> Người chơi đã được gán vào bàn.</li>
            <li><strong className="legend-amber">Khung cam / vàng:</strong> Người đứng ngoài bàn, vị trí tranh chấp (AMBIGUOUS) hoặc gậy bi-a.</li>
            <li><strong className="legend-red">Chấm đỏ viền trắng:</strong> Điểm chân đứng (Foot Anchor) dùng để gán bàn.</li>
            <li><strong className="legend-blue">Vùng viền bàn:</strong> Vùng mặt nỉ (Play) và vùng đứng đánh (Standing).</li>
          </ul>
        </div>
      </div>

      <div className="live-side-column">
        <VideoAutomationPanel
          onJumpCalibration={onJumpCalibration}
          onNotice={onNotice}
          onError={onError}
        />

        <div className="live-card">
          <div className="section-heading live-status-heading">
            <h2>Trạng thái camera và model</h2>
            <span className={`status ${data.camera_ready ? 'active' : 'closed'}`}>
              {data.camera_ready ? 'CÓ HÌNH' : 'ĐANG DỪNG'}
            </span>
          </div>

          <dl className="system-grid live-status-grid">
            <div><dt>Trạng thái</dt><dd><b>{data.camera_status ?? '—'}</b></dd></div>
            <div><dt>Chế độ nguồn</dt><dd>{data.mode}</dd></div>
            <div><dt>Đầu vào model</dt><dd>640 × 640 (khi model được nạp)</dd></div>
            <div>
              <dt>Model người</dt>
              <dd>{data.model_status.person.loaded ? `${data.model_status.person.name} · ${data.model_status.person.backend}` : 'Chưa nạp weights; không có nhận diện người'}</dd>
            </div>
            <div>
              <dt>Model gậy</dt>
              <dd>{data.model_status.cue.backend === 'DISABLED' ? 'Đã tắt để ưu tiên FPS (chế độ nhanh)' : data.model_status.cue.loaded ? `${data.model_status.cue.name} · ${data.model_status.cue.backend} (chưa kiểm chứng)` : 'Chưa nạp weights gậy'}</dd>
            </div>
          </dl>

          <div className="camera-toggle-grid live-camera-actions">
            <button
              type="button"
              className="button primary"
              disabled={locked || data.camera_ready}
              onClick={onStartCamera}
            >
              Bật Camera
            </button>
            <button
              type="button"
              className="button subtle"
              disabled={locked || !data.camera_ready}
              onClick={onStopCamera}
            >
              Dừng Camera
            </button>
          </div>

          <button
            type="button"
            className="button subtle full-width live-calibration-btn"
            onClick={onJumpCalibration}
          >
            Chuyển sang Hiệu chuẩn ROI ⛶
          </button>
        </div>
      </div>
    </section>
    </div>
  );
}
