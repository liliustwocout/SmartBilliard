import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import type { CalibrationConfig, CalibrationResponse, TableZoneConfig, ZoneOverlapWarning } from './types';

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 540;

type Mode = 'play' | 'standing';

export function RoiEditor({ onSaved }: { onSaved?: () => void }) {
  const [config, setConfig] = useState<CalibrationConfig | null>(null);
  const [overlaps, setOverlaps] = useState<ZoneOverlapWarning[]>([]);
  const [selectedTable, setSelectedTable] = useState<number>(1);
  const [activeMode, setActiveMode] = useState<Mode>('play');
  const [previewKey, setPreviewKey] = useState<number>(Date.now());
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [notice, setNotice] = useState<string>('');
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request<CalibrationResponse>('/calibration/zones')
      .then(res => {
        if (!cancelled) {
          setConfig(res.config);
          setOverlaps(res.overlaps);
        }
      })
      .catch(err => {
        if (!cancelled) setError(err.message || 'Không thể tải cấu hình ROI');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentTable: TableZoneConfig | undefined = config?.tables.find(t => t.table_id === selectedTable);

  const getPoints = (table: TableZoneConfig, mode: Mode): [number, number][] => {
    return mode === 'play' ? table.play_polygon : table.standing_polygon;
  };

  const updatePoints = (newPoints: [number, number][]) => {
    if (!config) return;
    const updatedTables = config.tables.map(t => {
      if (t.table_id !== selectedTable) return t;
      return {
        ...t,
        [activeMode === 'play' ? 'play_polygon' : 'standing_polygon']: newPoints,
      };
    });
    setConfig({ ...config, tables: updatedTables });
  };

  const getSvgCoordinates = (e: React.MouseEvent<SVGSVGElement>): [number, number] | null => {
    if (!svgRef.current) return null;
    const rect = svgRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingIdx !== null || !currentTable) return;
    const coords = getSvgCoordinates(e);
    if (!coords) return;

    const points = [...getPoints(currentTable, activeMode), coords];
    updatePoints(points);
    setNotice(`Đã thêm đỉnh (${coords[0].toFixed(2)}, ${coords[1].toFixed(2)})`);
  };

  const handleVertexMouseDown = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    setDraggingIdx(idx);
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingIdx === null || !currentTable) return;
    const coords = getSvgCoordinates(e);
    if (!coords) return;

    const currentPoints = [...getPoints(currentTable, activeMode)];
    currentPoints[draggingIdx] = coords;
    updatePoints(currentPoints);
  };

  const handleSvgMouseUp = () => {
    setDraggingIdx(null);
  };

  const handleVertexDoubleClick = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    if (!currentTable) return;
    const currentPoints = getPoints(currentTable, activeMode);
    if (currentPoints.length <= 3) {
      setError('Đa giác phải có tối thiểu 3 đỉnh, không thể xóa thêm.');
      return;
    }
    const filtered = currentPoints.filter((_, i) => i !== idx);
    updatePoints(filtered);
    setNotice(`Đã xóa đỉnh #${idx + 1}`);
  };

  const resetToDefault = () => {
    if (!currentTable) return;
    // Default rectangular shape for current table
    const offset = (selectedTable - 1) % 4;
    const col = offset % 2;
    const row = Math.floor(offset / 2);
    const baseX = col === 0 ? 0.12 : 0.65;
    const baseY = row === 0 ? 0.12 : 0.65;
    const play: [number, number][] = [
      [baseX, baseY],
      [baseX + 0.23, baseY],
      [baseX + 0.23, baseY + 0.23],
      [baseX, baseY + 0.23],
    ];
    const standing: [number, number][] = [
      [Math.max(0, baseX - 0.09), Math.max(0, baseY - 0.09)],
      [Math.min(1, baseX + 0.32), Math.max(0, baseY - 0.09)],
      [Math.min(1, baseX + 0.32), Math.min(1, baseY + 0.32)],
      [Math.max(0, baseX - 0.09), Math.min(1, baseY + 0.32)],
    ];
    const updated = config!.tables.map(t => (t.table_id === selectedTable ? { ...t, play_polygon: play, standing_polygon: standing } : t));
    setConfig({ ...config!, tables: updated });
    setNotice(`Đã đặt lại đa giác mặc định cho Bàn ${selectedTable}`);
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const res = await request<CalibrationResponse>('/calibration/zones', config);
      setConfig(res.config);
      setOverlaps(res.overlaps);
      setNotice(res.message || 'Lưu cấu hình ROI thành công!');
      if (onSaved) onSaved();
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Lỗi lưu cấu hình');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="detail-panel"><p>Đang tải dữ liệu hiệu chuẩn ROI…</p></div>;
  }

  const activePoints = currentTable ? getPoints(currentTable, activeMode) : [];

  return (
    <div className="roi-editor-container">
      <div className="section-heading">
        <div>
          <h2>Công cụ Hiệu chuẩn Vùng Bàn (ROI Editor · SB-10)</h2>
          <p>
            Vẽ và căn chỉnh đa giác mặt nỉ (Play) và vùng đứng đánh (Standing) chuẩn hóa [0..1] trên khung hình camera tham chiếu.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="button subtle" onClick={() => setPreviewKey(Date.now())}>
            Tải lại ảnh camera
          </button>
          <button className="button primary" disabled={saving} onClick={handleSave}>
            {saving ? 'Đang lưu…' : 'Lưu cấu hình ROI'}
          </button>
        </div>
      </div>

      {error && (
        <div className="message error" role="alert">
          {error}
          <button onClick={() => setError('')} aria-label="Đóng">×</button>
        </div>
      )}
      {notice && (
        <div className="message success" role="status">
          {notice}
          <button onClick={() => setNotice('')} aria-label="Đóng">×</button>
        </div>
      )}

      {overlaps.length > 0 && (
        <div className="message warning" role="alert">
          <strong>Cảnh báo giao thoa vùng đứng (AMBIGUOUS):</strong>
          <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0 }}>
            {overlaps.map((o, idx) => (
              <li key={idx}>{o.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="roi-layout" style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '1.5rem', marginTop: '1rem' }}>
        {/* Viewport */}
        <div
          className="roi-viewport"
          style={{
            position: 'relative',
            background: '#0d1117',
            borderRadius: '8px',
            overflow: 'hidden',
            border: '1px solid #30363d',
            userSelect: 'none',
          }}
        >
          {/* Reference Image */}
          <img
            src={`/api/calibration/preview?t=${previewKey}`}
            alt="Camera Preview"
            style={{ width: '100%', height: 'auto', display: 'block', pointerEvents: 'none' }}
          />

          {/* SVG Overlay */}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              cursor: draggingIdx !== null ? 'grabbing' : 'crosshair',
            }}
            onClick={handleSvgClick}
            onMouseMove={handleSvgMouseMove}
            onMouseUp={handleSvgMouseUp}
            onMouseLeave={handleSvgMouseUp}
          >
            {/* Render inactive tables */}
            {config?.tables.map(table => {
              if (table.table_id === selectedTable) return null;
              const playPts = table.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
              const standPts = table.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
              return (
                <g key={table.table_id} opacity={0.35}>
                  <polygon points={standPts} fill="#f59e0b" fillOpacity={0.08} stroke="#f59e0b" strokeWidth={1} strokeDasharray="3 3" />
                  <polygon points={playPts} fill="#10b981" fillOpacity={0.15} stroke="#10b981" strokeWidth={1.5} />
                  <text
                    x={table.play_polygon[0][0] * VIEW_WIDTH + 8}
                    y={table.play_polygon[0][1] * VIEW_HEIGHT + 18}
                    fill="#8b949e"
                    fontSize="12"
                    fontWeight="bold"
                  >
                    Bàn {table.table_id}
                  </text>
                </g>
              );
            })}

            {/* Render selected table */}
            {currentTable && (
              <g key={`selected-${currentTable.table_id}`}>
                {/* Standing zone */}
                <polygon
                  points={currentTable.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill="#f59e0b"
                  fillOpacity={activeMode === 'standing' ? 0.22 : 0.1}
                  stroke="#f59e0b"
                  strokeWidth={activeMode === 'standing' ? 2.5 : 1}
                  strokeDasharray={activeMode === 'standing' ? undefined : '4 4'}
                />

                {/* Play zone */}
                <polygon
                  points={currentTable.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill="#10b981"
                  fillOpacity={activeMode === 'play' ? 0.3 : 0.15}
                  stroke="#10b981"
                  strokeWidth={activeMode === 'play' ? 2.5 : 1.5}
                />

                {/* Editable vertices for active layer */}
                {activePoints.map(([x, y], idx) => {
                  const px = x * VIEW_WIDTH;
                  const py = y * VIEW_HEIGHT;
                  const isHovered = draggingIdx === idx;
                  const color = activeMode === 'play' ? '#10b981' : '#f59e0b';
                  return (
                    <g key={idx}>
                      <circle
                        cx={px}
                        cy={py}
                        r={isHovered ? 8 : 6}
                        fill={color}
                        stroke="#ffffff"
                        strokeWidth={2}
                        style={{ cursor: 'pointer' }}
                        onMouseDown={e => handleVertexMouseDown(e, idx)}
                        onDoubleClick={e => handleVertexDoubleClick(e, idx)}
                      />
                      <text x={px + 9} y={py + 4} fill="#ffffff" fontSize="11" fontWeight="bold">
                        {idx + 1}
                      </text>
                    </g>
                  );
                })}
              </g>
            )}
          </svg>
        </div>

        {/* Controls Sidebar */}
        <div className="roi-controls" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="detail-panel" style={{ padding: '1rem' }}>
            <label htmlFor="roi-table-select">Chọn bàn hiệu chuẩn</label>
            <select
              id="roi-table-select"
              value={selectedTable}
              onChange={e => setSelectedTable(Number(e.target.value))}
              style={{ width: '100%', marginBottom: '1rem' }}
            >
              {config?.tables.map(t => (
                <option key={t.table_id} value={t.table_id}>
                  Bàn {t.table_id.toString().padStart(2, '0')}
                </option>
              ))}
            </select>

            <p style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', color: '#8b949e' }}>CHỌN LỚP VÙNG (LAYER)</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1rem' }}>
              <button
                type="button"
                className={`button ${activeMode === 'play' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.85rem', padding: '0.5rem' }}
                onClick={() => setActiveMode('play')}
              >
                Mặt nỉ ({currentTable?.play_polygon.length || 0})
              </button>
              <button
                type="button"
                className={`button ${activeMode === 'standing' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.85rem', padding: '0.5rem' }}
                onClick={() => setActiveMode('standing')}
              >
                Vùng đứng ({currentTable?.standing_polygon.length || 0})
              </button>
            </div>

            <button type="button" className="button subtle full-width" onClick={resetToDefault} style={{ marginBottom: '0.5rem' }}>
              Khôi phục mặc định bàn này
            </button>
          </div>

          <div className="detail-panel" style={{ padding: '1rem' }}>
            <p style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', color: '#8b949e' }}>HƯỚNG DẪN THAO TÁC</p>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.8rem', color: '#c9d1d9', lineHeight: 1.5 }}>
              <li><strong>Click chuột</strong> vào ảnh để thêm đỉnh mới.</li>
              <li><strong>Kéo đỉnh</strong> để điều chỉnh tọa độ.</li>
              <li><strong>Nhấp đúp vào đỉnh</strong> để xóa đỉnh đó (tối thiểu 3 đỉnh).</li>
              <li>Tọa độ tự động chuẩn hóa từ <code>0.00</code> đến <code>1.00</code>.</li>
            </ul>
          </div>

          <div className="detail-panel" style={{ padding: '1rem' }}>
            <p style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', color: '#8b949e' }}>DANH SÁCH ĐỈNH HIỆN TẠI</p>
            <div style={{ maxHeight: '140px', overflowY: 'auto', fontSize: '0.75rem', fontFamily: 'monospace' }}>
              {activePoints.map(([x, y], idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                  <span>#{idx + 1}</span>
                  <span>[{x.toFixed(3)}, {y.toFixed(3)}]</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
