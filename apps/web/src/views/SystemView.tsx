import { money } from '../format';
import type { Snapshot } from '../types';
import { SettingsEditor } from './SettingsEditor';

export type SystemViewProps = {
  data: Snapshot;
  locked?: boolean;
  onNotice?: (message: string) => void;
  onError?: (message: string) => void;
};

export function SystemView({ data, locked, onNotice, onError }: SystemViewProps) {
  const needsConfirmCount = data.tables.filter(item => item.status === 'NEEDS_CONFIRMATION').length;

  return (
    <div className="system-view">
      <section className="stats-grid" aria-label="Thống kê từ máy chủ">
        <div className="stat">
          <span>Bàn đang hoạt động</span>
          <strong>{data.active_count}<small>/ {data.tables.length}</small></strong>
          <p><i className="dot green" />{data.tables.length - data.active_count} bàn chưa có phiên</p>
        </div>
        <div className="stat">
          <span>Tiền phiên đang chơi</span>
          <strong>{money(data.running_amount_vnd)}</strong>
          <p>Tạm tính bởi backend · làm tròn phút</p>
        </div>
        <div className="stat">
          <span>Doanh thu demo đã chốt</span>
          <strong>{money(data.revenue_vnd)}</strong>
          <p>Tổng hóa đơn đã lưu trên máy này</p>
        </div>
        <div className="stat">
          <span>Chờ nhân viên xác nhận</span>
          <strong className="text-amber">{needsConfirmCount.toString().padStart(2, '0')}</strong>
          <p>{data.auto_open_enabled ? 'Tự mở mô phỏng đã bật' : 'Tự động mở bàn đang tắt'}</p>
        </div>
      </section>

      <section className="system-panel">
        <div className="section-heading">
          <h2>Trạng thái triển khai Phase 2</h2>
          <span className="outline-badge">OFFLINE READY</span>
        </div>
        <dl className="system-grid">
          <div>
            <dt>Nguồn dữ liệu</dt>
            <dd>{data.mode === 'SIMULATED' ? 'Sự kiện mô phỏng / nhân viên' : 'Nhân viên'}</dd>
          </div>
          <div>
            <dt>Camera / tracking / ROI</dt>
            <dd>Chưa triển khai · Phase 3</dd>
          </div>
          <div>
            <dt>Nhận diện gậy</dt>
            <dd>Chưa có model được kiểm chứng</dd>
          </div>
          <div>
            <dt>Chính sách</dt>
            <dd>{data.decision_config.policy}</dd>
          </div>
          <div>
            <dt>Tự mở bàn demo</dt>
            <dd>{data.auto_open_enabled ? 'Đã bật' : 'Đã tắt · yêu cầu nhân viên'}</dd>
          </div>
          <div>
            <dt>Thời gian hiện diện</dt>
            <dd>{data.decision_config.presence_seconds} giây</dd>
          </div>
          <div>
            <dt>Confidence vào / giữ</dt>
            <dd>{data.decision_config.confidence_enter} / {data.decision_config.confidence_exit}</dd>
          </div>
          <div>
            <dt>Khoảng cách tín hiệu tối đa</dt>
            <dd>{data.decision_config.max_observation_gap_seconds} giây</dd>
          </div>
          <div>
            <dt>Khoảng vắng được làm mượt</dt>
            <dd>{data.decision_config.absence_grace_seconds} giây</dd>
          </div>
          <div>
            <dt>Cooldown sau chốt</dt>
            <dd>{data.decision_config.cooldown_seconds} giây</dd>
          </div>
          <div>
            <dt>Múi giờ hiển thị</dt>
            <dd>{data.timezone}</dd>
          </div>
          <div>
            <dt>Lưu trữ &amp; đồng bộ</dt>
            <dd>SQLite cục bộ · WebSocket</dd>
          </div>
        </dl>
        <div className="message warning">
          Camera, vẽ polygon và hai chế độ REAL_CLUB / MINI_TABLE nằm ngoài Phase 2. Ngưỡng, tự mở bàn, nguồn camera và giá giờ chỉnh ngay bên dưới.
        </div>
      </section>

      <SettingsEditor data={data} locked={locked} onNotice={onNotice} onError={onError} />
    </div>
  );
}
