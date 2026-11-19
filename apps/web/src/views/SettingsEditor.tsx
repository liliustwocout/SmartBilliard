import { useEffect, useState } from 'react';
import { request } from '../api';
import { money } from '../format';
import type { DecisionSettings, RuntimeSettings, Snapshot } from '../types';

type NumericKey = Exclude<keyof DecisionSettings, 'policy'>;

const FIELDS: Array<{ key: NumericKey; label: string; unit: string; step: number; hint: string }> = [
  { key: 'presence_seconds', label: 'Thời gian hiện diện', unit: 'giây', step: 0.5, hint: 'Phải thấy người chơi liên tục chừng này mới gợi ý mở bàn.' },
  { key: 'confidence_enter', label: 'Confidence để vào', unit: '0–1', step: 0.01, hint: 'Phải ≥ confidence giữ.' },
  { key: 'confidence_exit', label: 'Confidence để giữ', unit: '0–1', step: 0.01, hint: 'Ngưỡng thấp hơn khi đã nhận diện được.' },
  { key: 'max_observation_gap_seconds', label: 'Khoảng cách tín hiệu tối đa', unit: 'giây', step: 0.5, hint: 'Mất tín hiệu quá lâu thì xóa trạng thái ứng viên.' },
  { key: 'absence_grace_seconds', label: 'Khoảng vắng được làm mượt', unit: 'giây', step: 0.5, hint: 'Người ra khỏi vùng ngắn không bị tính là rời bàn.' },
  { key: 'cooldown_seconds', label: 'Cooldown sau thanh toán', unit: 'giây', step: 1, hint: 'AI không gợi ý lại bàn ngay sau khi chốt.' },
  { key: 'unbilled_alert_seconds', label: 'Cảnh báo quên mở bàn sau', unit: 'giây', step: 10, hint: 'Chơi quá lâu mà chưa mở thì báo đỏ.' },
  { key: 'playing_hold_grace_seconds', label: 'Giữ trạng thái đang chơi', unit: 'giây', step: 1, hint: 'Cho phép gián đoạn ngắn khi đang đánh.' },
  { key: 'cue_confidence', label: 'Confidence gậy', unit: '0–1', step: 0.01, hint: 'Chỉ dùng khi có model gậy đã kiểm chứng.' },
];

const POLICIES: Array<[DecisionSettings['policy'], string]> = [
  ['PERSON_ONLY', 'Chỉ người (PERSON_ONLY)'],
  ['PERSON_AND_CUE', 'Người + gậy (cần model gậy)'],
  ['POSE_AND_CUE', 'Tư thế + gậy (cần model gậy)'],
];

export type SettingsEditorProps = {
  data: Snapshot;
  locked?: boolean;
  onNotice?: (message: string) => void;
  onError?: (message: string) => void;
};

export function SettingsEditor({ data, locked = false, onNotice = () => {}, onError = () => {} }: SettingsEditorProps) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [policy, setPolicy] = useState<DecisionSettings['policy']>('PERSON_ONLY');
  const [source, setSource] = useState('');
  const [rates, setRates] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);

  function load(next: RuntimeSettings) {
    setSettings(next);
    setDraft(Object.fromEntries(FIELDS.map(f => [f.key, String(next.decision[f.key])])));
    setPolicy(next.decision.policy);
    setSource(next.camera_source);
  }

  useEffect(() => {
    let cancelled = false;
    request<RuntimeSettings>('/settings')
      .then(next => { if (!cancelled) load(next); })
      .catch(reason => { if (!cancelled) onError(String((reason as Error).message)); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save(body: unknown, message: string) {
    setSaving(true);
    try {
      load(await request<RuntimeSettings>('/settings', body));
      onNotice(message);
    } catch (reason) {
      onError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function saveThresholds() {
    if (!settings) return;
    const changes: Record<string, number | string> = {};
    for (const field of FIELDS) {
      const value = Number(draft[field.key]);
      if (draft[field.key]?.trim() === '' || !Number.isFinite(value)) {
        onError(`"${field.label}" phải là số.`);
        return;
      }
      if (value !== settings.decision[field.key]) changes[field.key] = value;
    }
    if (policy !== settings.decision.policy) changes.policy = policy;
    if (!Object.keys(changes).length) { onNotice('Không có thay đổi nào để lưu.'); return; }
    void save({ decision: changes }, 'Đã lưu ngưỡng nhận diện, có hiệu lực ngay.');
  }

  function setOpenMode(auto: boolean) {
    if (auto && !window.confirm('Chuyển sang AI tự động hoàn toàn: hệ thống sẽ tự tạo phiên tính tiền khi AI thấy đang chơi. AI chưa được kiểm chứng ngoài thực tế và có thể mở nhầm bàn. Tiếp tục?')) return;
    void save({ auto_open: auto, confirm_auto_open: auto }, auto ? 'Đã chuyển sang chế độ AI tự động mở bàn.' : 'Đã chuyển sang chế độ người duyệt.');
  }

  async function reset() {
    if (!window.confirm('Khôi phục ngưỡng, tự mở bàn và nguồn camera về mặc định từ file cấu hình? Giá giờ từng bàn không bị đổi.')) return;
    setSaving(true);
    try {
      load(await request<RuntimeSettings>('/settings/reset', {}));
      onNotice('Đã khôi phục cấu hình mặc định.');
    } catch (reason) {
      onError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function cameraAction(path: '/camera/start' | '/camera/stop', message: string) {
    try { await request(path, {}); onNotice(message); } catch (reason) { onError((reason as Error).message); }
  }

  async function saveRate(tableId: number, current: number) {
    const raw = rates[tableId];
    const value = Number(raw);
    if (raw === undefined || raw.trim() === '' || !Number.isInteger(value) || value < 0) {
      onError('Giá giờ phải là số nguyên VND, không âm.');
      return;
    }
    if (value === current) return;
    try {
      await request(`/tables/${tableId}/rate`, { hourly_rate: value });
      setRates(prev => { const next = { ...prev }; delete next[tableId]; return next; });
      onNotice(`Đã đổi giá giờ bàn ${tableId} thành ${money(value)}. Phiên đang chạy giữ giá đã chốt.`);
    } catch (reason) {
      onError((reason as Error).message);
    }
  }

  if (!settings) {
    return <section className="settings-panel"><p className="empty-inline" role="status">Đang tải cấu hình…</p></section>;
  }
  const busy = saving || locked;
  const sourceChanged = source.trim() !== settings.camera_source;

  return (
    <section className="settings-panel" aria-label="Chỉnh cấu hình trực tiếp">
      <div className="section-heading">
        <div>
          <h2>Chỉnh cấu hình trực tiếp</h2>
          <p>Có hiệu lực ngay, không cần khởi động lại. {settings.persisted ? 'Lưu trong data/runtime_settings.json, không ghi đè decision.toml hay .env.' : 'Cơ sở dữ liệu tạm: thay đổi không được lưu qua lần khởi động.'}</p>
        </div>
        <button type="button" className="button subtle" disabled={busy || settings.overridden.length === 0} onClick={() => void reset()}>
          Khôi phục mặc định
        </button>
      </div>

      <div className="settings-block">
        <h3>Ngưỡng nhận diện</h3>
        <div className="settings-grid">
          {FIELDS.map(field => (
            <label key={field.key} className="settings-field">
              <span>{field.label} <small>({field.unit})</small></span>
              <input type="number" inputMode="decimal" step={field.step} value={draft[field.key] ?? ''}
                onChange={event => setDraft(prev => ({ ...prev, [field.key]: event.target.value }))} />
              <small>{field.hint} Mặc định: {settings.decision_defaults[field.key]}</small>
            </label>
          ))}
          <label className="settings-field">
            <span>Chính sách quyết định</span>
            <select value={policy} onChange={event => setPolicy(event.target.value as DecisionSettings['policy'])}>
              {POLICIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <small>Hai chính sách có gậy sẽ không mở được khi chưa có model gậy được kiểm chứng.</small>
          </label>
        </div>
        <button type="button" className="button primary" disabled={busy} onClick={saveThresholds}>Lưu ngưỡng</button>
      </div>

      <div className="settings-block">
        <h3>Chế độ mở bàn</h3>
        <div className="mode-options" role="radiogroup" aria-label="Chế độ mở bàn">
          <label className={`mode-option ${!settings.auto_open ? 'selected' : ''}`}>
            <input type="radio" name="open-mode" checked={!settings.auto_open} disabled={busy} onChange={() => setOpenMode(false)} />
            <span><strong>Người duyệt</strong>
              <small>AI chỉ gợi ý. Hiện cảnh báo kèm nút Xem camera / Xác nhận, nhân viên bấm mới mở bàn.</small></span>
          </label>
          <label className={`mode-option ${settings.auto_open ? 'selected' : ''}`}>
            <input type="radio" name="open-mode" checked={settings.auto_open} disabled={busy} onChange={() => setOpenMode(true)} />
            <span><strong>AI tự động hoàn toàn</strong>
              <small>AI tự mở bàn khi thấy đang chơi đủ lâu. Chỉ tự mở bàn: thanh toán và đóng phiên vẫn do nhân viên, AI không bao giờ tự đóng phiên.</small></span>
          </label>
        </div>
        <p className="footnote">AI chưa được kiểm chứng ngoài thực tế; chế độ tự động có thể mở nhầm bàn và tính tiền sai. Nên kiểm tra kỹ trước khi dùng cho khách thật.</p>
      </div>

      <div className="settings-block">
        <h3>Nguồn camera</h3>
        <label className="settings-field">
          <span>Camera / RTSP / đường dẫn video</span>
          <input type="text" value={source} placeholder="0, rtsp://…, data/recordings/x.mp4" onChange={event => setSource(event.target.value)} />
          <small>Mật khẩu trong URL được ẩn khi hiển thị. Nếu camera đang chạy, đổi nguồn sẽ khởi động lại luồng. Mặc định: {settings.camera_source_default}</small>
        </label>
        <div className="settings-actions">
          <button type="button" className="button primary" disabled={busy || !sourceChanged || !source.trim()}
            onClick={() => void save({ camera_source: source.trim() }, 'Đã đổi nguồn camera.')}>Lưu nguồn</button>
          <button type="button" className="button subtle" disabled={busy || data.camera_ready}
            onClick={() => void cameraAction('/camera/start', 'Đã bật camera.')}>Bật camera</button>
          <button type="button" className="button subtle" disabled={busy || !data.camera_ready}
            onClick={() => void cameraAction('/camera/stop', 'Đã dừng camera.')}>Dừng camera</button>
        </div>
      </div>

      <div className="settings-block">
        <h3>Giá giờ từng bàn</h3>
        <div className="settings-grid">
          {data.tables.map(item => (
            <div key={item.id} className="settings-field">
              <span>{item.name} <small>(VND / giờ · hiện {money(item.hourly_rate)})</small></span>
              <div className="settings-inline">
                <input type="number" min={0} step={1000} value={rates[item.id] ?? String(item.hourly_rate)}
                  onChange={event => setRates(prev => ({ ...prev, [item.id]: event.target.value }))} />
                <button type="button" className="button subtle" disabled={busy || rates[item.id] === undefined || Number(rates[item.id]) === item.hourly_rate}
                  onClick={() => void saveRate(item.id, item.hourly_rate)}>Lưu</button>
              </div>
              {item.session && <small>Phiên đang chạy giữ giá đã chốt lúc mở bàn.</small>}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
