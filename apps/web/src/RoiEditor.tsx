import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import type { CalibrationConfig, CalibrationResponse, TableZoneConfig, ZoneOverlapWarning } from './types';

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 540;

type Mode = 'play' | 'standing';
type ToolMode = 'select' | 'add';

export function RoiEditor({ onSaved }: { onSaved?: () => void }) {
  const [config, setConfig] = useState<CalibrationConfig | null>(null);
  const [overlaps, setOverlaps] = useState<ZoneOverlapWarning[]>([]);
  const [selectedTable, setSelectedTable] = useState<number>(1);
  const [activeMode, setActiveMode] = useState<Mode>('play');
  const [toolMode, setToolMode] = useState<ToolMode>('select');
  const [previewKey, setPreviewKey] = useState<number>(Date.now());
  const [useLiveStream, setUseLiveStream] = useState<boolean>(false);
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [selectedVertex, setSelectedVertex] = useState<number | null>(null);
  const [isTranslating, setIsTranslating] = useState<boolean>(false);
  const [dragStartCoords, setDragStartCoords] = useState<[number, number] | null>(null);
  const [syncStanding, setSyncStanding] = useState<boolean>(true);
  const [hideOtherTables, setHideOtherTables] = useState<boolean>(false);
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

  // Keyboard shortcut: Delete vertex on 'Delete' or 'Backspace'
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedVertex !== null) {
        e.preventDefault();
        deleteSelectedVertex();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedVertex, config, selectedTable, activeMode]);

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

  const getSvgCoordinates = (e: React.MouseEvent): [number, number] | null => {
    if (!svgRef.current) return null;
    const rect = svgRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
  };

  // Click on SVG viewport
  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingIdx !== null || isTranslating || !currentTable) return;

    if (toolMode === 'add') {
      const coords = getSvgCoordinates(e);
      if (!coords) return;
      const points = [...getPoints(currentTable, activeMode), coords];
      updatePoints(points);
      setSelectedVertex(points.length - 1);
      setNotice(`Đã thêm đỉnh #${points.length} tại [${coords[0].toFixed(3)}, ${coords[1].toFixed(3)}]`);
    } else {
      // In select mode, clicking empty space deselects vertex
      setSelectedVertex(null);
    }
  };

  // Vertex Dragging
  const handleVertexMouseDown = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    setDraggingIdx(idx);
    setSelectedVertex(idx);
  };

  // Whole-polygon Translation (Move entire table zone)
  const handlePolygonMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    const coords = getSvgCoordinates(e);
    if (!coords) return;
    setIsTranslating(true);
    setDragStartCoords(coords);
    setSelectedVertex(null);
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!currentTable || !config) return;

    // 1. Drag single vertex
    if (draggingIdx !== null) {
      const coords = getSvgCoordinates(e);
      if (!coords) return;
      const currentPoints = [...getPoints(currentTable, activeMode)];
      currentPoints[draggingIdx] = coords;
      updatePoints(currentPoints);
      return;
    }

    // 2. Translate entire polygon
    if (isTranslating && dragStartCoords) {
      const currentCoords = getSvgCoordinates(e);
      if (!currentCoords) return;

      const dx = currentCoords[0] - dragStartCoords[0];
      const dy = currentCoords[1] - dragStartCoords[1];

      if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) return;

      const translatePoly = (poly: [number, number][]): [number, number][] => {
        const minX = Math.min(...poly.map(p => p[0]));
        const maxX = Math.max(...poly.map(p => p[0]));
        const minY = Math.min(...poly.map(p => p[1]));
        const maxY = Math.max(...poly.map(p => p[1]));

        const clampedDx = Math.max(-minX, Math.min(1 - maxX, dx));
        const clampedDy = Math.max(-minY, Math.min(1 - maxY, dy));

        return poly.map(([x, y]) => [
          Math.round((x + clampedDx) * 1000) / 1000,
          Math.round((y + clampedDy) * 1000) / 1000,
        ]);
      };

      const updatedTables = config.tables.map(t => {
        if (t.table_id !== selectedTable) return t;

        if (activeMode === 'play') {
          const newPlay = translatePoly(t.play_polygon);
          const newStanding = syncStanding ? translatePoly(t.standing_polygon) : t.standing_polygon;
          return { ...t, play_polygon: newPlay, standing_polygon: newStanding };
        } else {
          const newStanding = translatePoly(t.standing_polygon);
          return { ...t, standing_polygon: newStanding };
        }
      });

      setConfig({ ...config, tables: updatedTables });
      setDragStartCoords(currentCoords);
    }
  };

  const handleSvgMouseUp = () => {
    setDraggingIdx(null);
    setIsTranslating(false);
    setDragStartCoords(null);
  };

  // Delete Vertex
  const deleteSelectedVertex = () => {
    if (!currentTable || selectedVertex === null) return;
    const currentPoints = getPoints(currentTable, activeMode);
    if (currentPoints.length <= 3) {
      setError('Đa giác phải có tối thiểu 3 đỉnh để xác định vùng hợp lệ.');
      return;
    }
    const filtered = currentPoints.filter((_, i) => i !== selectedVertex);
    updatePoints(filtered);
    setSelectedVertex(null);
    setNotice('Đã xóa đỉnh đã chọn.');
  };

  // Utilities & Presets
  const createStandardRectangle = () => {
    if (!currentTable) return;
    const pts = getPoints(currentTable, activeMode);
    const cx = pts.length > 0 ? pts.reduce((acc, p) => acc + p[0], 0) / pts.length : 0.35;
    const cy = pts.length > 0 ? pts.reduce((acc, p) => acc + p[1], 0) / pts.length : 0.35;
    const halfW = activeMode === 'play' ? 0.12 : 0.18;
    const halfH = activeMode === 'play' ? 0.11 : 0.17;

    const rect: [number, number][] = [
      [Math.max(0, Math.round((cx - halfW) * 1000) / 1000), Math.max(0, Math.round((cy - halfH) * 1000) / 1000)],
      [Math.min(1, Math.round((cx + halfW) * 1000) / 1000), Math.max(0, Math.round((cy - halfH) * 1000) / 1000)],
      [Math.min(1, Math.round((cx + halfW) * 1000) / 1000), Math.min(1, Math.round((cy + halfH) * 1000) / 1000)],
      [Math.max(0, Math.round((cx - halfW) * 1000) / 1000), Math.min(1, Math.round((cy + halfH) * 1000) / 1000)],
    ];
    updatePoints(rect);
    setSelectedVertex(null);
    setNotice(`Đã tạo hình chữ nhật chuẩn 4 đỉnh cho ${activeMode === 'play' ? 'mặt nỉ' : 'vùng đứng'}`);
  };

  const generateStandingFromPlay = () => {
    if (!currentTable || !config) return;
    const play = currentTable.play_polygon;
    if (play.length < 3) return;
    const cx = play.reduce((acc, p) => acc + p[0], 0) / play.length;
    const cy = play.reduce((acc, p) => acc + p[1], 0) / play.length;

    const standing = play.map(([x, y]) => {
      const dx = x - cx;
      const dy = y - cy;
      return [
        Math.max(0, Math.min(1, Math.round((cx + dx * 1.35) * 1000) / 1000)),
        Math.max(0, Math.min(1, Math.round((cy + dy * 1.35) * 1000) / 1000)),
      ] as [number, number];
    });

    const updatedTables = config.tables.map(t =>
      t.table_id === selectedTable ? { ...t, standing_polygon: standing } : t
    );
    setConfig({ ...config, tables: updatedTables });
    setNotice(`Đã tự động tạo vùng đứng bao quanh mặt nỉ (+35%) cho Bàn ${selectedTable}`);
  };

  const scalePolygon = (factor: number) => {
    if (!currentTable) return;
    const pts = getPoints(currentTable, activeMode);
    if (pts.length < 3) return;
    const cx = pts.reduce((acc, p) => acc + p[0], 0) / pts.length;
    const cy = pts.reduce((acc, p) => acc + p[1], 0) / pts.length;
    const scaled = pts.map(([x, y]) => [
      Math.max(0, Math.min(1, Math.round((cx + (x - cx) * factor) * 1000) / 1000)),
      Math.max(0, Math.min(1, Math.round((cy + (y - cy) * factor) * 1000) / 1000)),
    ] as [number, number]);
    updatePoints(scaled);
    setNotice(`Đã ${factor > 1 ? 'mở rộng' : 'thu nhỏ'} vùng ${activeMode === 'play' ? 'mặt nỉ' : 'vùng đứng'} ${Math.round(Math.abs(factor - 1) * 100)}%`);
  };

  const resetToDefault = () => {
    if (!currentTable || !config) return;
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
      [Math.max(0, baseX - 0.08), Math.max(0, baseY - 0.08)],
      [Math.min(1, baseX + 0.31), Math.max(0, baseY - 0.08)],
      [Math.min(1, baseX + 0.31), Math.min(1, baseY + 0.31)],
      [Math.max(0, baseX - 0.08), Math.min(1, baseY + 0.31)],
    ];
    const updated = config.tables.map(t => (t.table_id === selectedTable ? { ...t, play_polygon: play, standing_polygon: standing } : t));
    setConfig({ ...config, tables: updated });
    setSelectedVertex(null);
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
      setNotice(res.message || 'Lưu cấu hình ROI thành công! Hệ thống camera đã tự động áp dụng vùng mới.');
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
          <h2>Công cụ Hiệu chuẩn Vùng Bàn (ROI Editor · Nâng cấp)</h2>
          <p>
            Căn chỉnh đa giác mặt nỉ (Play) và vùng đứng (Standing). Kéo rê chuột vào thân đa giác để di chuyển cả bàn.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            type="button"
            className={`button ${useLiveStream ? 'primary' : 'subtle'}`}
            onClick={() => setUseLiveStream(!useLiveStream)}
            title="Bật stream trực tiếp từ camera làm ảnh nền hiệu chuẩn"
          >
            {useLiveStream ? '● Stream camera trực tiếp' : 'Ảnh nền tĩnh'}
          </button>
          <button
            type="button"
            className="button subtle"
            onClick={() => {
              setPreviewKey(Date.now());
              setNotice('Đã chụp frame mới từ camera');
            }}
          >
            Chụp lại ảnh nền
          </button>
          <button type="button" className="button primary" disabled={saving} onClick={handleSave}>
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

      {/* Table Selector Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.85rem', color: '#8b949e', fontWeight: 600, marginRight: '0.25rem' }}>BÀN HIỆU CHUẨN:</span>
        {config?.tables.map(t => (
          <button
            key={t.table_id}
            type="button"
            className={`button ${selectedTable === t.table_id ? 'primary' : 'subtle'}`}
            style={{ padding: '0.35rem 0.85rem', fontSize: '0.85rem' }}
            onClick={() => {
              setSelectedTable(t.table_id);
              setSelectedVertex(null);
            }}
          >
            Bàn {t.table_id.toString().padStart(2, '0')}
          </button>
        ))}
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: '#c9d1d9', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={hideOtherTables}
            onChange={e => setHideOtherTables(e.target.checked)}
          />
          Chỉ hiện bàn đang chọn
        </label>
      </div>

      <div className="roi-layout" style={{ display: 'grid', gridTemplateColumns: '1fr 310px', gap: '1.25rem', marginTop: '0.75rem' }}>
        {/* Main Viewport */}
        <div
          className="roi-viewport"
          style={{
            position: 'relative',
            background: '#090d13',
            borderRadius: '8px',
            overflow: 'hidden',
            border: '1px solid #30363d',
            userSelect: 'none',
          }}
        >
          {/* Reference Background Feed */}
          {useLiveStream ? (
            <img
              src="/api/camera/stream"
              alt="Camera Stream Live"
              style={{ width: '100%', height: 'auto', display: 'block', pointerEvents: 'none' }}
            />
          ) : (
            <img
              src={`/api/calibration/preview?t=${previewKey}`}
              alt="Camera Calibration Preview"
              style={{ width: '100%', height: 'auto', display: 'block', pointerEvents: 'none' }}
            />
          )}

          {/* SVG Interaction Layer */}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              cursor: isTranslating ? 'grabbing' : toolMode === 'add' ? 'crosshair' : 'default',
            }}
            onClick={handleSvgClick}
            onMouseMove={handleSvgMouseMove}
            onMouseUp={handleSvgMouseUp}
            onMouseLeave={handleSvgMouseUp}
          >
            {/* Inactive tables */}
            {!hideOtherTables &&
              config?.tables.map(table => {
                if (table.table_id === selectedTable) return null;
                const playPts = table.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
                const standPts = table.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
                return (
                  <g key={table.table_id} opacity={0.35} style={{ cursor: 'pointer' }} onClick={() => setSelectedTable(table.table_id)}>
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

            {/* Selected Active Table */}
            {currentTable && (
              <g key={`selected-${currentTable.table_id}`}>
                {/* Standing Zone Polygon */}
                <polygon
                  points={currentTable.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill="#f59e0b"
                  fillOpacity={activeMode === 'standing' ? 0.28 : 0.08}
                  stroke="#f59e0b"
                  strokeWidth={activeMode === 'standing' ? 2.5 : 1}
                  strokeDasharray={activeMode === 'standing' ? undefined : '4 4'}
                  style={{ cursor: activeMode === 'standing' ? (isTranslating ? 'grabbing' : 'grab') : 'pointer' }}
                  onMouseDown={activeMode === 'standing' ? handlePolygonMouseDown : undefined}
                />

                {/* Play Zone Polygon */}
                <polygon
                  points={currentTable.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill="#10b981"
                  fillOpacity={activeMode === 'play' ? 0.35 : 0.15}
                  stroke="#10b981"
                  strokeWidth={activeMode === 'play' ? 3 : 1.5}
                  style={{ cursor: activeMode === 'play' ? (isTranslating ? 'grabbing' : 'grab') : 'pointer' }}
                  onMouseDown={activeMode === 'play' ? handlePolygonMouseDown : undefined}
                />

                {/* Table Label Badge on Canvas */}
                <text
                  x={currentTable.play_polygon[0][0] * VIEW_WIDTH + 8}
                  y={currentTable.play_polygon[0][1] * VIEW_HEIGHT + 20}
                  fill="#ffffff"
                  fontSize="13"
                  fontWeight="bold"
                  filter="drop-shadow(0px 1px 2px rgba(0,0,0,0.8))"
                  style={{ pointerEvents: 'none' }}
                >
                  BÀN {currentTable.table_id.toString().padStart(2, '0')} {isTranslating ? '(Đang di chuyển…)' : ''}
                </text>

                {/* Vertices of Active Layer */}
                {activePoints.map(([x, y], idx) => {
                  const px = x * VIEW_WIDTH;
                  const py = y * VIEW_HEIGHT;
                  const isHovered = draggingIdx === idx;
                  const isSelected = selectedVertex === idx;
                  const color = activeMode === 'play' ? '#10b981' : '#f59e0b';
                  return (
                    <g key={idx}>
                      {/* Selection ring */}
                      {isSelected && (
                        <circle
                          cx={px}
                          cy={py}
                          r={15}
                          fill="none"
                          stroke="#38bdf8"
                          strokeWidth={2}
                          strokeDasharray="3 3"
                        />
                      )}
                      {/* Interactive Vertex Handle (Larger hit area: r=10) */}
                      <circle
                        cx={px}
                        cy={py}
                        r={isHovered ? 12 : 9}
                        fill={color}
                        stroke="#ffffff"
                        strokeWidth={2.5}
                        style={{ cursor: 'pointer', filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.6))' }}
                        onMouseDown={e => handleVertexMouseDown(e, idx)}
                      />
                      {/* Vertex Index Label */}
                      <text
                        x={px + 12}
                        y={py + 5}
                        fill="#ffffff"
                        fontSize="12"
                        fontWeight="bold"
                        filter="drop-shadow(0px 1px 2px rgba(0,0,0,0.9))"
                        style={{ pointerEvents: 'none' }}
                      >
                        {idx + 1}
                      </text>
                    </g>
                  );
                })}
              </g>
            )}
          </svg>
        </div>

        {/* Sidebar Controls */}
        <div className="roi-controls" style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {/* Mode & Tools Panel */}
          <div className="detail-panel" style={{ padding: '0.85rem' }}>
            <p style={{ margin: '0 0 0.5rem', fontSize: '0.8rem', color: '#8b949e', fontWeight: 600 }}>CHỌN LỚP ĐIỀU CHỈNH</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginBottom: '0.8rem' }}>
              <button
                type="button"
                className={`button ${activeMode === 'play' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.82rem', padding: '0.45rem' }}
                onClick={() => {
                  setActiveMode('play');
                  setSelectedVertex(null);
                }}
              >
                Mặt nỉ ({currentTable?.play_polygon.length || 0})
              </button>
              <button
                type="button"
                className={`button ${activeMode === 'standing' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.82rem', padding: '0.45rem' }}
                onClick={() => {
                  setActiveMode('standing');
                  setSelectedVertex(null);
                }}
              >
                Vùng đứng ({currentTable?.standing_polygon.length || 0})
              </button>
            </div>

            <p style={{ margin: '0 0 0.4rem', fontSize: '0.8rem', color: '#8b949e', fontWeight: 600 }}>CHẾ ĐỘ THAO TÁC</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginBottom: '0.6rem' }}>
              <button
                type="button"
                className={`button ${toolMode === 'select' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.8rem', padding: '0.4rem' }}
                onClick={() => setToolMode('select')}
                title="Kéo đỉnh hoặc kéo cả bàn"
              >
                Chọn & Kéo bàn
              </button>
              <button
                type="button"
                className={`button ${toolMode === 'add' ? 'primary' : 'subtle'}`}
                style={{ fontSize: '0.8rem', padding: '0.4rem' }}
                onClick={() => setToolMode('add')}
                title="Click lên ảnh để thêm đỉnh mới"
              >
                ＋ Thêm đỉnh
              </button>
            </div>

            {activeMode === 'play' && (
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: '#c9d1d9', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={syncStanding}
                  onChange={e => setSyncStanding(e.target.checked)}
                />
                Kéo cả vùng đứng khi di chuyển mặt nỉ
              </label>
            )}
          </div>

          {/* Quick Preset Actions */}
          <div className="detail-panel" style={{ padding: '0.85rem' }}>
            <p style={{ margin: '0 0 0.5rem', fontSize: '0.8rem', color: '#8b949e', fontWeight: 600 }}>CÔNG CỤ CĂN NHANH</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              <button type="button" className="button subtle full-width" style={{ fontSize: '0.82rem' }} onClick={createStandardRectangle}>
                Tạo hình chữ nhật chuẩn (4 đỉnh)
              </button>
              <button type="button" className="button subtle full-width" style={{ fontSize: '0.82rem' }} onClick={generateStandingFromPlay}>
                Sinh vùng đứng bao quanh tự động (+35%)
              </button>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                <button type="button" className="button subtle" style={{ fontSize: '0.8rem' }} onClick={() => scalePolygon(1.1)}>
                  Mở rộng +10%
                </button>
                <button type="button" className="button subtle" style={{ fontSize: '0.8rem' }} onClick={() => scalePolygon(0.9)}>
                  Thu nhỏ -10%
                </button>
              </div>
              {selectedVertex !== null && (
                <button type="button" className="button danger full-width" style={{ fontSize: '0.8rem' }} onClick={deleteSelectedVertex}>
                  Xóa đỉnh #{selectedVertex + 1} đang chọn
                </button>
              )}
              <button type="button" className="button subtle full-width" style={{ fontSize: '0.8rem', color: '#f87171' }} onClick={resetToDefault}>
                Khôi phục mặc định ban đầu
              </button>
            </div>
          </div>

          {/* Instructions */}
          <div className="detail-panel" style={{ padding: '0.85rem' }}>
            <p style={{ margin: '0 0 0.4rem', fontSize: '0.8rem', color: '#8b949e', fontWeight: 600 }}>MẸO THAO TÁC TIỆN LỢI</p>
            <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.78rem', color: '#c9d1d9', lineHeight: 1.5 }}>
              <li><strong>Di chuyển cả bàn:</strong> Bấm giữ chuột vào <em>lòng đa giác</em> rồi kéo rê.</li>
              <li><strong>Di chuyển đỉnh:</strong> Bấm giữ chuột vào <em>điểm tròn</em> rồi kéo.</li>
              <li><strong>Chỉ cần căn mặt nỉ:</strong> Xong bấm <em>"Sinh vùng đứng bao quanh"</em> là hoàn tất 2 lớp!</li>
              <li><strong>Xóa đỉnh:</strong> Bấm vào đỉnh rồi nhấn phím <code>Delete</code> hoặc nút xóa.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
