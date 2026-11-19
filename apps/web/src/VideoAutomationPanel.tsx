import { useEffect, useRef, useState } from 'react';
import { request, uploadVideoFile } from './api';
import type {
  DatasetManifest,
  VideoEvaluationReport,
  VideoListResponse,
  VideoUploadResponse,
} from './types';

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function VideoAutomationPanel({
  compact = false,
  onJumpCalibration,
  onNotice,
  onError,
}: {
  compact?: boolean;
  onJumpCalibration?: () => void;
  onNotice?: (message: string) => void;
  onError?: (message: string) => void;
}) {
  const [videoInfo, setVideoInfo] = useState<VideoListResponse | null>(null);
  const [autoStart, setAutoStart] = useState(true);
  const [autoEvaluate, setAutoEvaluate] = useState(true);
  const [working, setWorking] = useState('');
  const [evaluation, setEvaluation] = useState<VideoEvaluationReport | null>(null);
  const [datasetManifest, setDatasetManifest] = useState<DatasetManifest | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refreshVideos() {
    try {
      const data = await request<VideoListResponse>('/videos');
      setVideoInfo(data);
    } catch {
      // Ignore transient poll errors while offline
    }
  }

  useEffect(() => {
    void refreshVideos();
  }, []);

  async function runAction<T>(label: string, work: () => Promise<T>): Promise<T | null> {
    setWorking(label);
    onError?.('');
    try {
      const res = await work();
      await refreshVideos();
      return res;
    } catch (reason) {
      onError?.((reason as Error).message);
      return null;
    } finally {
      setWorking('');
    }
  }

  async function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const res = await runAction('Đang tải video lên và tự động chạy AI...', () =>
      uploadVideoFile<VideoUploadResponse>(file, { autoStart, autoEvaluate }),
    );
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (res) {
      if (res.evaluation) setEvaluation(res.evaluation);
      onNotice?.(
        `Đã xử lý xong "${res.filename}" (${formatBytes(res.size_bytes)})${res.live_started ? ' và đang phát Live trên POS.' : '.'}`,
      );
    }
  }

  async function handleGenerateDemo() {
    const res = await runAction('Đang tạo video mẫu và chạy phân tích AI...', () =>
      request<VideoUploadResponse>('/videos/generate-demo', { duration_seconds: 30 }, 180000),
    );
    if (res) {
      if (res.evaluation) setEvaluation(res.evaluation);
      onNotice?.(`Đã tạo & kích hoạt video mẫu "${res.filename}".`);
    }
  }

  async function handleActivate(filename: string) {
    const res = await runAction(`Đang bật "${filename}" lên Live POS...`, () =>
      request<{ success: boolean; status: string }>('/videos/activate', { filename }, 20000),
    );
    if (res) {
      onNotice?.(`Đã chuyển nguồn Live POS sang "${filename}" (${res.status}).`);
    }
  }

  async function handleEvaluate(filename: string) {
    const report = await runAction(`Đang phân tích tua nhanh "${filename}"...`, () =>
      request<VideoEvaluationReport>('/videos/evaluate', { filename }, 180000),
    );
    if (report) {
      setEvaluation(report);
      onNotice?.(`Đã phân tích xong "${filename}" (${report.processing_fps} FPS xử lý).`);
    }
  }

  async function handleExtractDataset(filename: string) {
    const manifest = await runAction(`Đang tách frame train từ "${filename}"...`, () =>
      request<DatasetManifest>('/videos/extract-dataset', { filename, interval: 2.0 }, 180000),
    );
    if (manifest) {
      setDatasetManifest(manifest);
      onNotice?.(`Đã tách ${manifest.total_images} ảnh vào dataset "${manifest.dataset_id}".`);
    }
  }

  async function handleDelete(filename: string, active: boolean) {
    const promptText = active
      ? `Video "${filename}" đang phát Live. Dừng luồng và xoá file này khỏi bộ nhớ cục bộ?`
      : `Xoá video "${filename}" khỏi danh sách đã lưu?`;
    if (!window.confirm(promptText)) return;
    const res = await runAction(`Đang xoá "${filename}"...`, () =>
      request<{ deleted: boolean; filename: string; stopped_live: boolean }>('/videos/delete', { filename }),
    );
    if (res) {
      setEvaluation(prev => {
        if (!prev) return prev;
        const normalized = prev.video_path.replace(/\\/g, '/');
        return normalized.endsWith(`/${res.filename}`) || normalized === res.filename ? null : prev;
      });
      onNotice?.(
        `Đã xoá video "${res.filename}"${res.stopped_live ? ' và dừng luồng Live đang phát.' : '.'}`,
      );
    }
  }

  const busy = working !== '';

  return (
    <section className="simulation-panel video-automation-panel">
      <div className="section-heading">
        <h2>Tải Video &amp; Tự động hóa AI</h2>
        <span className="outline-badge">1-CLICK</span>
      </div>
      <p>
        Chọn file video từ máy tính (<code>.mp4</code>, <code>.avi</code>, <code>.mkv</code>) để tự động lưu, phát Live POS và chấm trạng thái bàn.
      </p>

      <div className="video-upload-box">
        <input
          ref={fileInputRef}
          id={compact ? 'video-upload-compact' : 'video-upload-live'}
          type="file"
          accept="video/*,.mp4,.avi,.mkv,.mov,.webm"
          disabled={busy}
          onChange={e => void handleFileSelect(e)}
          style={{ display: 'none' }}
        />
        <button
          type="button"
          className="button primary full-width"
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
        >
          {busy ? working : '⬆ Tải Video lên & Tự động xử lý'}
        </button>

        <div className="video-auto-options">
          <label className="checkbox-label">
            <input type="checkbox" checked={autoStart} disabled={busy} onChange={e => setAutoStart(e.target.checked)} />
            Tự chạy Live POS
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={autoEvaluate} disabled={busy} onChange={e => setAutoEvaluate(e.target.checked)} />
            Tự phân tích tua nhanh
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: onJumpCalibration ? '1fr 1fr' : '1fr', gap: '6px' }}>
          <button type="button" className="button subtle" disabled={busy} onClick={() => void handleGenerateDemo()}>
            Tạo Video Mẫu (1-Click)
          </button>
          {onJumpCalibration && (
            <button type="button" className="button subtle" disabled={busy} onClick={onJumpCalibration}>
              Căn ROI theo Video ⛶
            </button>
          )}
        </div>
      </div>

      {videoInfo && (
        <div className="model-status-row">
          <span>
            Pose/Person: <strong className={videoInfo.models.pose || videoInfo.models.person ? 'text-green' : 'text-amber'}>
              {videoInfo.models.pose ? 'Có file YOLOv8n-pose' : videoInfo.models.person ? 'Có file YOLOv8n' : 'Chưa có weights'}
            </strong>
          </span>
          <span>
            Gậy: <strong className={videoInfo.models.cue ? 'text-green' : 'text-amber'}>
              {videoInfo.models.cue ? 'Có file weights (chưa kiểm chứng)' : 'Chưa có weights'}
            </strong>
          </span>
        </div>
      )}

      <div className="video-library">
        <div className="video-library-header">
          <span>Video đã lưu ({videoInfo?.videos.length ?? 0})</span>
          <button type="button" className="link-btn" disabled={busy} onClick={() => void refreshVideos()}>
            Làm mới
          </button>
        </div>
        {!videoInfo || videoInfo.videos.length === 0 ? (
          <p className="empty-inline" style={{ padding: '8px 0' }}>
            Chưa có video nào. Hãy tải video lên hoặc bấm &ldquo;Tạo Video Mẫu&rdquo;.
          </p>
        ) : (
          <div className="video-list">
            {videoInfo.videos.map(item => (
              <div key={item.filename} className={`video-item ${item.active ? 'active' : ''}`}>
                <div className="video-item-meta">
                  <strong title={item.filename}>{item.filename}</strong>
                  <small>
                    {formatBytes(item.size_bytes)} {item.active ? '· ĐANG PHÁT LIVE' : ''}
                  </small>
                </div>
                <div className="video-item-actions">
                  <button type="button" className="button subtle" disabled={busy} onClick={() => void handleActivate(item.filename)}>
                    Phát Live
                  </button>
                  <button type="button" className="button subtle" disabled={busy} onClick={() => void handleEvaluate(item.filename)}>
                    Phân tích
                  </button>
                  <button type="button" className="button subtle" disabled={busy} onClick={() => void handleExtractDataset(item.filename)}>
                    Tách Frame
                  </button>
                  <button type="button" className="button danger" disabled={busy} onClick={() => void handleDelete(item.filename, item.active)}>
                    Xoá
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {evaluation && (
        <div className="eval-report-box">
          <div className="video-library-header">
            <strong>Kết quả phân tích tua nhanh</strong>
            <span>{evaluation.processing_fps} FPS ({evaluation.person_pose_backend})</span>
          </div>
          <p style={{ fontSize: '10px', color: 'var(--muted)', marginBottom: '8px' }}>
            Thời lượng: {evaluation.video_duration_seconds}s · Đã xử lý {evaluation.processed_frames} khung hình trong {evaluation.wall_seconds}s
          </p>
          {!evaluation.person_pose_model_ready && (
            <p className="eval-warn">
              Chưa có file <code>models/yolov8n-pose.onnx</code> hoặc <code>yolov8n.onnx</code> nên kết quả AI đang ở chế độ dự phòng (0 detection).
            </p>
          )}
          <div className="eval-tables">
            {Object.entries(evaluation.tables).map(([tid, st]) => (
              <div key={tid} className="eval-table-row">
                <div>
                  <strong>Bàn {tid.padStart(2, '0')}</strong>
                  <small>Trạng thái cuối: {st.final_state}</small>
                </div>
                <div className="eval-metrics">
                  <span className="text-green">Đánh: {st.PLAYING_seconds}s</span>
                  <span>Không chơi: {st.NOT_PLAYING_seconds}s</span>
                  <span>Chưa rõ: {st.UNKNOWN_seconds}s</span>
                  {st.unbilled_alert_triggered && (
                    <span className="text-red">Cảnh báo &gt;5p @ {st.first_unbilled_alert_at_s}s</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {datasetManifest && (
        <div className="eval-report-box">
          <div className="video-library-header">
            <strong>Dataset Train đã tách ({datasetManifest.dataset_id})</strong>
            <span>{datasetManifest.total_images} ảnh</span>
          </div>
          <p style={{ fontSize: '10px', color: 'var(--muted)', lineHeight: 1.5 }}>
            Train: <b>{datasetManifest.split_counts.train}</b> · Val: <b>{datasetManifest.split_counts.val}</b> · Test: <b>{datasetManifest.split_counts.test}</b>
            <br />
            Config: <code>{datasetManifest.dataset_yaml}</code>
          </p>
        </div>
      )}
    </section>
  );
}
