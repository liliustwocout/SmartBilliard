import { useEffect, useRef, useState } from 'react';
import type { SyntheticEvent } from 'react';
import { request } from './api';
import type { AutoCalibrationResponse, CalibrationConfig, CalibrationResponse, TableZoneConfig, ZoneOverlapWarning } from './types';

const DEFAULT_VIEW_WIDTH = 960;
const DEFAULT_VIEW_HEIGHT = 540;

type Mode = 'play' | 'standing';
type ToolMode = 'select' | 'add';
type Point2D = [number, number];

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, round3(value)));
}

function ccw(a: Point2D, b: Point2D, c: Point2D): boolean {
  return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0]);
}

function segmentsIntersect(p1: Point2D, p2: Point2D, p3: Point2D, p4: Point2D): boolean {
  if (
    (p1[0] === p3[0] && p1[1] === p3[1]) ||
    (p1[0] === p4[0] && p1[1] === p4[1]) ||
    (p2[0] === p3[0] && p2[1] === p3[1]) ||
    (p2[0] === p4[0] && p2[1] === p4[1])
  ) {
    return false;
  }
  return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && ccw(p1, p2, p3) !== ccw(p1, p2, p4);
}

export function pointInPolygon(point: Point2D, poly: Point2D[]): boolean {
  const [x, y] = point;
  const n = poly.length;
  if (n < 3) return false;
  let inside = false;
  let [p1x, p1y] = poly[0];
  for (let i = 1; i <= n; i += 1) {
    const [p2x, p2y] = poly[i % n];
    if (y > Math.min(p1y, p2y) && y <= Math.max(p1y, p2y) && x <= Math.max(p1x, p2x)) {
      const xints = p1y !== p2y ? ((y - p1y) * (p2x - p1x)) / (p2y - p1y) + p1x : x;
      if (p1x === p2x || x <= xints) {
        inside = !inside;
      }
    }
    p1x = p2x;
    p1y = p2y;
  }
  return inside;
}

export function polygonsOverlap(polyA: Point2D[], polyB: Point2D[]): boolean {
  if (polyA.length < 3 || polyB.length < 3) return false;
  for (let i = 0; i < polyA.length; i += 1) {
    const a1 = polyA[i];
    const a2 = polyA[(i + 1) % polyA.length];
    for (let j = 0; j < polyB.length; j += 1) {
      const b1 = polyB[j];
      const b2 = polyB[(j + 1) % polyB.length];
      if (segmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  for (const p of polyA) {
    if (pointInPolygon(p, polyB)) return true;
  }
  for (const p of polyB) {
    if (pointInPolygon(p, polyA)) return true;
  }
  return false;
}

export function detectLocalOverlaps(tables: TableZoneConfig[]): ZoneOverlapWarning[] {
  const enabled = tables.filter(t => t.enabled);
  const warnings: ZoneOverlapWarning[] = [];
  for (let i = 0; i < enabled.length; i += 1) {
    for (let j = i + 1; j < enabled.length; j += 1) {
      const a = enabled[i];
      const b = enabled[j];
      if (polygonsOverlap(a.standing_polygon, b.standing_polygon)) {
        warnings.push({
          table_a: a.table_id,
          table_b: b.table_id,
          message: `Vùng đứng của Bàn ${a.table_id} và Bàn ${b.table_id} bị giao nhau. Vùng giao này sẽ kích hoạt trạng thái AMBIGUOUS khi có người xuất hiện.`,
        });
      }
    }
  }
  return warnings;
}

export function alignPerspectivePolygon(poly: Point2D[]): Point2D[] {
  if (poly.length !== 4) return poly;
  const [p0, p1, p2, p3] = poly;

  const midTop: Point2D = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
  const midBottom: Point2D = [(p3[0] + p2[0]) / 2, (p3[1] + p2[1]) / 2];
  const midLeft: Point2D = [(p0[0] + p3[0]) / 2, (p0[1] + p3[1]) / 2];
  const midRight: Point2D = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2];

  const lenTop = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
  const lenBottom = Math.hypot(p2[0] - p3[0], p2[1] - p3[1]);
  const lenLeft = Math.hypot(p3[0] - p0[0], p3[1] - p0[1]);
  const lenRight = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);

  const isHorizontal = (lenTop + lenBottom) >= (lenLeft + lenRight);

  if (isHorizontal) {
    const axisV = [midBottom[0] - midTop[0], midBottom[1] - midTop[1]];
    const axisLen = Math.hypot(axisV[0], axisV[1]) || 1;
    // Normal vector pointing rightwards from vertical axis
    const normX = axisV[1] / axisLen;
    const normY = -axisV[0] / axisLen;

    const avgTop = (lenTop + lenBottom * 0.9) / 2;
    const avgBottom = (lenBottom + lenTop * 1.1) / 2;
    const halfTop = avgTop / 2;
    const halfBottom = avgBottom / 2;

    return [
      [clamp01(midTop[0] - normX * halfTop), clamp01(midTop[1] - normY * halfTop)],
      [clamp01(midTop[0] + normX * halfTop), clamp01(midTop[1] + normY * halfTop)],
      [clamp01(midBottom[0] + normX * halfBottom), clamp01(midBottom[1] + normY * halfBottom)],
      [clamp01(midBottom[0] - normX * halfBottom), clamp01(midBottom[1] - normY * halfBottom)],
    ];
  } else {
    const axisH = [midRight[0] - midLeft[0], midRight[1] - midLeft[1]];
    const axisLen = Math.hypot(axisH[0], axisH[1]) || 1;
    // Normal vector pointing downwards from horizontal axis
    const normX = -axisH[1] / axisLen;
    const normY = axisH[0] / axisLen;

    const avgLeft = (lenLeft + lenRight * 0.9) / 2;
    const avgRight = (lenRight + lenLeft * 1.1) / 2;
    const halfLeft = avgLeft / 2;
    const halfRight = avgRight / 2;

    return [
      [clamp01(midLeft[0] - normX * halfLeft), clamp01(midLeft[1] - normY * halfLeft)],
      [clamp01(midRight[0] - normX * halfRight), clamp01(midRight[1] - normY * halfRight)],
      [clamp01(midRight[0] + normX * halfRight), clamp01(midRight[1] + normY * halfRight)],
      [clamp01(midLeft[0] + normX * halfLeft), clamp01(midLeft[1] + normY * halfLeft)],
    ];
  }
}

export function buildNonOverlappingStandingPolygon(
  playPolygon: Point2D[],
  otherStandingPolygons: Point2D[][],
  defaultScale = 1.35,
): Point2D[] {
  if (playPolygon.length < 3) return playPolygon;
  const cx = playPolygon.reduce((acc, p) => acc + p[0], 0) / playPolygon.length;
  const cy = playPolygon.reduce((acc, p) => acc + p[1], 0) / playPolygon.length;
  const baseScale = Math.max(1.05, Math.min(1.8, defaultScale));
  const scaleSteps = [baseScale, baseScale * 0.94, baseScale * 0.88, baseScale * 0.82, 1.12, 1.05, 1.03].filter(
    (v, i, arr) => v >= 1.03 && arr.indexOf(v) === i,
  );

  const scalePt = (x: number, y: number, s: number): Point2D => {
    const persp = 1.0 + (y - cy) * 0.15;
    const clampedS = 1.0 + (s - 1.0) * Math.max(0.85, Math.min(1.25, persp));
    return [
      clamp01(cx + (x - cx) * clampedS),
      clamp01(cy + (y - cy) * clampedS),
    ];
  };

  const vertexScales = playPolygon.map(([x, y]) => {
    for (const s of scaleSteps) {
      const candidate = scalePt(x, y, s);
      if (!otherStandingPolygons.some(other => pointInPolygon(candidate, other))) {
        return s;
      }
    }
    return 1.03;
  });

  for (const maxScale of scaleSteps) {
    const candidatePoly = playPolygon.map(([x, y], idx) =>
      scalePt(x, y, Math.min(vertexScales[idx], maxScale)),
    );
    if (!otherStandingPolygons.some(other => polygonsOverlap(candidatePoly, other))) {
      return candidatePoly;
    }
  }

  return playPolygon.map(([x, y]) => scalePt(x, y, 1.03));
}

const DEFAULT_SLOTS: Array<[number, number, number, number]> = [
  [0.08, 0.12, 0.28, 0.34],
  [0.38, 0.12, 0.58, 0.34],
  [0.68, 0.12, 0.88, 0.34],
  [0.08, 0.52, 0.28, 0.74],
  [0.38, 0.52, 0.58, 0.74],
  [0.68, 0.52, 0.88, 0.74],
  [0.23, 0.33, 0.43, 0.54],
  [0.54, 0.33, 0.74, 0.54],
];

export function createDefaultTableZone(tableId: number, existingTables: TableZoneConfig[]): TableZoneConfig {
  const otherStanding = existingTables.map(t => t.standing_polygon);
  const startIdx = (Math.max(1, tableId) - 1) % DEFAULT_SLOTS.length;

  for (let step = 0; step < DEFAULT_SLOTS.length; step += 1) {
    const [x1, y1, x2, y2] = DEFAULT_SLOTS[(startIdx + step) % DEFAULT_SLOTS.length];
    const play: Point2D[] = [
      [x1, y1],
      [x2, y1],
      [x2, y2],
      [x1, y2],
    ];
    const standing = buildNonOverlappingStandingPolygon(play, otherStanding, 1.3);
    if (!otherStanding.some(other => polygonsOverlap(standing, other))) {
      return {
        table_id: tableId,
        enabled: true,
        play_polygon: play,
        standing_polygon: standing,
      };
    }
  }

  const [x1, y1, x2, y2] = DEFAULT_SLOTS[startIdx];
  const play: Point2D[] = [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
  return {
    table_id: tableId,
    enabled: true,
    play_polygon: play,
    standing_polygon: buildNonOverlappingStandingPolygon(play, otherStanding, 1.3),
  };
}

export function getNextUncalibratedTableId(tables: TableZoneConfig[], tableCount: number): number | null {
  const maxTables = Math.max(1, Math.min(8, tableCount));
  for (let id = 1; id <= maxTables; id += 1) {
    if (!tables.some(t => t.table_id === id)) return id;
  }
  return null;
}

export function addTableZoneToConfig(
  config: CalibrationConfig,
  tableId: number,
  tableCount: number,
): CalibrationConfig {
  const maxTables = Math.max(1, Math.min(8, tableCount));
  if (tableId < 1 || tableId > maxTables || config.tables.some(t => t.table_id === tableId)) {
    return config;
  }
  const zone = createDefaultTableZone(tableId, config.tables);
  return {
    ...config,
    tables: [...config.tables, zone].sort((a, b) => a.table_id - b.table_id),
  };
}

export function toggleTableEnabledInConfig(
  config: CalibrationConfig,
  tableId: number,
  enabled: boolean,
): CalibrationConfig {
  return {
    ...config,
    tables: config.tables.map(t => (t.table_id === tableId ? { ...t, enabled } : t)),
  };
}

export function removeTableZoneFromConfig(config: CalibrationConfig, tableId: number): CalibrationConfig {
  return {
    ...config,
    tables: config.tables.filter(t => t.table_id !== tableId),
  };
}

export function shouldRefreshRoiPreview(
  prev: { active: boolean; sourceKey: string },
  next: { active: boolean; sourceKey: string },
  hasAutoPreview: boolean,
): { clearAutoPreview: boolean; refreshPreview: boolean } {
  const sourceChanged = prev.sourceKey !== next.sourceKey;
  const becameActive = !prev.active && next.active;
  return {
    clearAutoPreview: sourceChanged,
    refreshPreview: next.active && (sourceChanged || (becameActive && !hasAutoPreview)),
  };
}

const CORNER_NAMES = [
  'Góc 1: Trên - Trái (Top-Left)',
  'Góc 2: Trên - Phải (Top-Right)',
  'Góc 3: Dưới - Phải (Bottom-Right)',
  'Góc 4: Dưới - Trái (Bottom-Left)',
];

export function RoiEditor({
  tableCount = 4,
  initialResponse,
  active = true,
  sourceKey = '',
  onSaved,
}: {
  tableCount?: number;
  initialResponse?: CalibrationResponse;
  active?: boolean;
  sourceKey?: string;
  onSaved?: () => void;
}) {
  const maxTables = Math.max(1, Math.min(8, tableCount));
  const [config, setConfig] = useState<CalibrationConfig | null>(initialResponse?.config ?? null);
  const [savedConfig, setSavedConfig] = useState<CalibrationConfig | null>(initialResponse?.config ?? null);
  const [viewSize, setViewSize] = useState({ width: DEFAULT_VIEW_WIDTH, height: DEFAULT_VIEW_HEIGHT });
  const [overlaps, setOverlaps] = useState<ZoneOverlapWarning[]>(initialResponse?.overlaps ?? []);
  const [selectedTable, setSelectedTable] = useState<number>(
    initialResponse?.config.tables[0]?.table_id ?? 1,
  );
  const [activeMode, setActiveMode] = useState<Mode>('play');
  const [toolMode, setToolMode] = useState<ToolMode>('select');
  const [previewKey, setPreviewKey] = useState<number>(Date.now());
  const [useLiveStream, setUseLiveStream] = useState<boolean>(false);
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [selectedVertex, setSelectedVertex] = useState<number | null>(null);
  const [isTranslating, setIsTranslating] = useState<boolean>(false);
  const [dragStartCoords, setDragStartCoords] = useState<Point2D | null>(null);
  const [syncStanding, setSyncStanding] = useState<boolean>(true);
  const [hideOtherTables, setHideOtherTables] = useState<boolean>(false);
  const [autoDetecting, setAutoDetecting] = useState<boolean>(false);
  const [loupeEnabled, setLoupeEnabled] = useState<boolean>(true);
  const [cursorCoords, setCursorCoords] = useState<Point2D | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialResponse);
  const [isCornerMode, setIsCornerMode] = useState<boolean>(false);
  const [cornerPoints, setCornerPoints] = useState<Point2D[]>([]);
  const [standingMargin, setStandingMargin] = useState<number>(30);

  const [saving, setSaving] = useState<boolean>(false);
  const [autoPreviewUrl, setAutoPreviewUrl] = useState<string | null>(null);
  const [autoWarnings, setAutoWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string>('');
  const [notice, setNotice] = useState<string>('');
  const svgRef = useRef<SVGSVGElement>(null);
  const configRef = useRef(config);
  configRef.current = config;
  const autoPreviewUrlRef = useRef<string | null>(autoPreviewUrl);
  autoPreviewUrlRef.current = autoPreviewUrl;
  const prevViewStateRef = useRef({ active, sourceKey });
  const VIEW_WIDTH = viewSize.width;
  const VIEW_HEIGHT = viewSize.height;
  const hasUnsavedChanges = config !== null && savedConfig !== null && JSON.stringify(config) !== JSON.stringify(savedConfig);

  useEffect(() => {
    const prev = prevViewStateRef.current;
    const next = { active, sourceKey };
    prevViewStateRef.current = next;
    const decision = shouldRefreshRoiPreview(prev, next, autoPreviewUrlRef.current !== null);
    if (decision.clearAutoPreview) {
      setAutoPreviewUrl(null);
      setAutoWarnings([]);
    }
    if (decision.refreshPreview) {
      setPreviewKey(current => Math.max(Date.now(), current + 1));
    }
  }, [active, sourceKey]);

  const handleImageLoad = (event: SyntheticEvent<HTMLImageElement>) => {
    const image = event.currentTarget;
    if (image.naturalWidth > 0 && image.naturalHeight > 0) {
      setViewSize(current => (current.width === image.naturalWidth && current.height === image.naturalHeight
        ? current
        : { width: image.naturalWidth, height: image.naturalHeight }));
    }
  };

  useEffect(() => {
    if (initialResponse) return;
    let cancelled = false;
    setLoading(true);
    request<CalibrationResponse>('/calibration/zones')
      .then(res => {
        if (!cancelled) {
          setConfig(res.config);
          setSavedConfig(res.config);
          setOverlaps(res.overlaps);
          if (res.config.tables.length > 0 && !res.config.tables.some(t => t.table_id === selectedTable)) {
            setSelectedTable(res.config.tables[0].table_id);
          }
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

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isCornerMode) {
          setIsCornerMode(false);
          setCornerPoints([]);
          setNotice('Đã hủy chế độ chấm 4 góc.');
        } else if (selectedVertex !== null) {
          setSelectedVertex(null);
        }
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selectedVertex !== null) {
        e.preventDefault();
        deleteSelectedVertex();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedVertex, config, selectedTable, activeMode, isCornerMode]);

  const currentTable: TableZoneConfig | undefined = config?.tables.find(t => t.table_id === selectedTable);
  const nextMissingId = config ? getNextUncalibratedTableId(config.tables, maxTables) : null;
  const liveOverlaps = config ? detectLocalOverlaps(config.tables) : [];
  const displayedOverlaps = hasUnsavedChanges ? liveOverlaps : (overlaps.length > 0 ? overlaps : liveOverlaps);

  const tableIds = Array.from(
    new Set([
      ...Array.from({ length: maxTables }, (_, i) => i + 1),
      ...(config?.tables.map(t => t.table_id) ?? []),
    ]),
  ).sort((a, b) => a - b);

  const getPoints = (table: TableZoneConfig, mode: Mode): Point2D[] => {
    return mode === 'play' ? table.play_polygon : table.standing_polygon;
  };

  const updatePoints = (newPoints: Point2D[]) => {
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

  const handleAddTable = (targetId: number) => {
    if (!config) return;
    const updated = addTableZoneToConfig(config, targetId, maxTables);
    if (updated === config) return;
    setConfig(updated);
    setSelectedTable(targetId);
    setSelectedVertex(null);
    setError('');
    setNotice(`Đã thêm vùng ROI mặc định cho Bàn ${targetId.toString().padStart(2, '0')}. Hãy căn chỉnh rồi bấm Lưu cấu hình ROI.`);
  };

  const handleToggleEnabled = (tableId: number, enabled: boolean) => {
    if (!config) return;
    setConfig(toggleTableEnabledInConfig(config, tableId, enabled));
    setError('');
    setNotice(
      enabled
        ? `Đã bật theo dõi AI cho Bàn ${tableId.toString().padStart(2, '0')} (bấm Lưu để áp dụng).`
        : `Đã tạm tắt theo dõi AI cho Bàn ${tableId.toString().padStart(2, '0')} (bấm Lưu để áp dụng).`,
    );
  };

  const handleDeleteTable = (tableId: number) => {
    if (!config) return;
    const label = `Bàn ${tableId.toString().padStart(2, '0')}`;
    if (!window.confirm(`Xóa vùng ROI của ${label}? Bàn sẽ không nhận tín hiệu AI cho tới khi hiệu chuẩn lại.`)) {
      return;
    }
    const updated = removeTableZoneFromConfig(config, tableId);
    setConfig(updated);
    setSelectedVertex(null);
    setError('');
    setNotice(`Đã xóa vùng ROI của ${label}. Bấm "Lưu cấu hình ROI" để áp dụng.`);
  };

  const getSvgCoordinates = (e: React.MouseEvent): Point2D | null => {
    if (!svgRef.current) return null;
    const rect = svgRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return [round3(x), round3(y)];
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isCornerMode) {
      const coords = getSvgCoordinates(e);
      if (!coords) return;
      const nextPoints = [...cornerPoints, coords];
      if (nextPoints.length < 4) {
        setCornerPoints(nextPoints);
        setNotice(`Đã chọn ${CORNER_NAMES[nextPoints.length - 1]}. Hãy click tiếp: ${CORNER_NAMES[nextPoints.length]}`);
      } else {
        const finalPlay = nextPoints;
        const otherStanding = config ? config.tables
          .filter(t => t.table_id !== selectedTable && t.enabled)
          .map(t => t.standing_polygon) : [];
        const finalStanding = buildNonOverlappingStandingPolygon(finalPlay, otherStanding, 1 + standingMargin / 100);
        const updated = config?.tables.map(t =>
          t.table_id === selectedTable
            ? { ...t, play_polygon: finalPlay, standing_polygon: finalStanding }
            : t,
        );
        if (config && updated) {
          setConfig({ ...config, tables: updated });
        }
        setIsCornerMode(false);
        setCornerPoints([]);
        setNotice(`🎯 Đã hoàn thành vẽ mặt nỉ 4 góc cho Bàn ${selectedTable}! Hãy kiểm tra và bấm 'Lưu cấu hình ROI'.`);
      }
      return;
    }

    if (draggingIdx !== null || isTranslating || !currentTable) return;

    if (toolMode === 'add') {
      const coords = getSvgCoordinates(e);
      if (!coords) return;
      const points = [...getPoints(currentTable, activeMode), coords];
      updatePoints(points);
      setSelectedVertex(points.length - 1);
      setNotice(`Đã thêm đỉnh #${points.length} tại [${coords[0].toFixed(3)}, ${coords[1].toFixed(3)}]`);
    } else {
      setSelectedVertex(null);
    }
  };

  const handleVertexMouseDown = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    setDraggingIdx(idx);
    setSelectedVertex(idx);
  };

  const handlePolygonMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    const coords = getSvgCoordinates(e);
    if (!coords) return;
    setIsTranslating(true);
    setDragStartCoords(coords);
    setSelectedVertex(null);
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const coords = getSvgCoordinates(e);
    if (coords) setCursorCoords(coords);
    if (!currentTable || !config) return;

    if (draggingIdx !== null) {
      if (!coords) return;
      const currentPoints = [...getPoints(currentTable, activeMode)];
      currentPoints[draggingIdx] = coords;
      updatePoints(currentPoints);
      return;
    }


    if (isTranslating && dragStartCoords) {
      const currentCoords = getSvgCoordinates(e);
      if (!currentCoords) return;

      const dx = currentCoords[0] - dragStartCoords[0];
      const dy = currentCoords[1] - dragStartCoords[1];

      if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) return;

      const translatePoly = (poly: Point2D[]): Point2D[] => {
        const minX = Math.min(...poly.map(p => p[0]));
        const maxX = Math.max(...poly.map(p => p[0]));
        const minY = Math.min(...poly.map(p => p[1]));
        const maxY = Math.max(...poly.map(p => p[1]));

        const clampedDx = Math.max(-minX, Math.min(1 - maxX, dx));
        const clampedDy = Math.max(-minY, Math.min(1 - maxY, dy));

        return poly.map(([x, y]) => [round3(x + clampedDx), round3(y + clampedDy)]);
      };

      const updatedTables = config.tables.map(t => {
        if (t.table_id !== selectedTable) return t;

        if (activeMode === 'play') {
          const newPlay = translatePoly(t.play_polygon);
          const newStanding = syncStanding ? translatePoly(t.standing_polygon) : t.standing_polygon;
          return { ...t, play_polygon: newPlay, standing_polygon: newStanding };
        }
        const newStanding = translatePoly(t.standing_polygon);
        return { ...t, standing_polygon: newStanding };
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

  const handleSvgMouseLeave = () => {
    setCursorCoords(null);
    handleSvgMouseUp();
  };


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

  const createStandardRectangle = () => {
    if (!currentTable) return;
    const pts = getPoints(currentTable, activeMode);
    const cx = pts.length > 0 ? pts.reduce((acc, p) => acc + p[0], 0) / pts.length : 0.35;
    const cy = pts.length > 0 ? pts.reduce((acc, p) => acc + p[1], 0) / pts.length : 0.35;
    const halfW = activeMode === 'play' ? 0.12 : 0.18;
    const halfH = activeMode === 'play' ? 0.11 : 0.17;

    const rect: Point2D[] = [
      [Math.max(0, round3(cx - halfW)), Math.max(0, round3(cy - halfH))],
      [Math.min(1, round3(cx + halfW)), Math.max(0, round3(cy - halfH))],
      [Math.min(1, round3(cx + halfW)), Math.min(1, round3(cy + halfH))],
      [Math.max(0, round3(cx - halfW)), Math.min(1, round3(cy + halfH))],
    ];
    updatePoints(rect);
    setSelectedVertex(null);
    setNotice(`Đã tạo hình chữ nhật chuẩn 4 đỉnh cho ${activeMode === 'play' ? 'mặt nỉ' : 'vùng đứng'}`);
  };

  const generateStandingFromPlay = () => {
    if (!currentTable || !config) return;
    const play = currentTable.play_polygon;
    if (play.length < 3) return;
    const otherStanding = config.tables
      .filter(t => t.table_id !== selectedTable && t.enabled)
      .map(t => t.standing_polygon);
    const standing = buildNonOverlappingStandingPolygon(play, otherStanding, 1.35);

    const updatedTables = config.tables.map(t =>
      t.table_id === selectedTable ? { ...t, standing_polygon: standing } : t,
    );
    setConfig({ ...config, tables: updatedTables });
    setNotice(
      otherStanding.length > 0
        ? `Đã tự động tạo vùng đứng quanh mặt nỉ (tránh vùng của bàn khác) cho Bàn ${selectedTable}`
        : `Đã tự động tạo vùng đứng bao quanh mặt nỉ (+35%) cho Bàn ${selectedTable}`,
    );
  };

  const scalePolygon = (factor: number) => {
    if (!currentTable) return;
    const pts = getPoints(currentTable, activeMode);
    if (pts.length < 3) return;
    const cx = pts.reduce((acc, p) => acc + p[0], 0) / pts.length;
    const cy = pts.reduce((acc, p) => acc + p[1], 0) / pts.length;
    const scaled = pts.map(([x, y]) => [
      clamp01(cx + (x - cx) * factor),
      clamp01(cy + (y - cy) * factor),
    ] as Point2D);
    updatePoints(scaled);
    setNotice(`Đã ${factor > 1 ? 'mở rộng' : 'thu nhỏ'} vùng ${activeMode === 'play' ? 'mặt nỉ' : 'vùng đứng'} ${Math.round(Math.abs(factor - 1) * 100)}%`);
  };

  const resetToDefault = () => {
    if (!currentTable || !config) return;
    const otherTables = config.tables.filter(t => t.table_id !== selectedTable);
    const resetZone = createDefaultTableZone(selectedTable, otherTables);
    const updated = config.tables.map(t =>
      t.table_id === selectedTable
        ? { ...t, play_polygon: resetZone.play_polygon, standing_polygon: resetZone.standing_polygon }
        : t,
    );
    setConfig({ ...config, tables: updated });
    setSelectedVertex(null);
    setNotice(`Đã đặt lại đa giác mặc định cho Bàn ${selectedTable}`);
  };

  const handleAutoDetect = async () => {
    if (!config) return;
    setAutoDetecting(true);
    setError('');
    setNotice('');
    try {
      const result = await request<AutoCalibrationResponse>('/calibration/auto-detect', config, 45000);
      if (configRef.current !== config) {
        setError('ROI đã thay đổi trong lúc nhận diện. Bấm Tự nhận diện bàn để thử lại trên bản đang chỉnh.');
        return;
      }
      setAutoPreviewUrl(result.preview_data_url);
      setUseLiveStream(false);
      setAutoWarnings(result.warnings);
      if (result.updated_table_ids.length === 0) {
        setError(result.message || 'Chưa tìm thấy mặt bàn đủ rõ.');
        return;
      }
      setConfig(result.config);
      setOverlaps(result.overlaps);
      setSelectedTable(result.updated_table_ids[0]);
      setSelectedVertex(null);
      setNotice(result.message || 'Đã tạo đề xuất ROI. Kiểm tra rồi bấm Lưu cấu hình ROI.');
    } catch (err: unknown) {
      setError((err as Error).message || 'Không thể tự nhận diện bàn.');
    } finally {
      setAutoDetecting(false);
    }
  };

  const handleOptimizeStandingZones = () => {
    if (!config) return;
    const newTables: TableZoneConfig[] = [];
    for (let i = 0; i < config.tables.length; i += 1) {
      const current = config.tables[i];
      const otherStandings = newTables
        .map(t => t.standing_polygon)
        .concat(config.tables.slice(i + 1).map(t => t.standing_polygon));
      const optimizedStanding = buildNonOverlappingStandingPolygon(
        current.play_polygon,
        otherStandings,
        1.28,
      );
      newTables.push({
        ...current,
        standing_polygon: optimizedStanding,
      });
    }
    setConfig({ ...config, tables: newTables });
    const localOvs = detectLocalOverlaps(newTables);
    setOverlaps(localOvs);
    setNotice(
      localOvs.length === 0
        ? 'Đã tự động tính toán lại vùng đứng cho tất cả các bàn (0 chồng lấn)!'
        : `Đã tối ưu vùng đứng cho các bàn (còn ${localOvs.length} vị trí chồng lấn).`,
    );
  };

  const handleStartCornerMode = () => {
    if (!currentTable) return;
    setIsCornerMode(true);
    setCornerPoints([]);
    setSelectedVertex(null);
    setIsTranslating(false);
    setDraggingIdx(null);
    setDragStartCoords(null);
    setActiveMode('play');
    setNotice('Chế độ chấm 4 góc đang bật: Hãy click lần lượt 4 góc mép nỉ (1. Trên-Trái, 2. Trên-Phải, 3. Dưới-Phải, 4. Dưới-Trái). Bấm ESC để hủy.');
  };

  const handleStandingMarginChange = (margin: number) => {
    setStandingMargin(margin);
    if (!currentTable || !config) return;
    const play = currentTable.play_polygon;
    const otherStanding = config.tables
      .filter(t => t.table_id !== selectedTable && t.enabled)
      .map(t => t.standing_polygon);
    const newStanding = buildNonOverlappingStandingPolygon(play, otherStanding, 1 + margin / 100);
    const updated = config.tables.map(t =>
      t.table_id === selectedTable ? { ...t, standing_polygon: newStanding } : t,
    );
    setConfig({ ...config, tables: updated });
  };

  const handleAlignPerspective = () => {
    if (!currentTable || !config) return;
    let poly = currentTable.play_polygon;
    if (poly.length !== 4) {
      if (poly.length < 3) {
        setError('Cần ít nhất 3 đỉnh để căn chỉnh phối cảnh.');
        return;
      }
      const xs = poly.map(p => p[0]);
      const ys = poly.map(p => p[1]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      poly = [
        [round3(minX), round3(minY)],
        [round3(maxX), round3(minY)],
        [round3(maxX), round3(maxY)],
        [round3(minX), round3(maxY)],
      ];
    }
    const alignedPlay = alignPerspectivePolygon(poly);
    const otherStanding = config.tables
      .filter(t => t.table_id !== selectedTable)
      .map(t => t.standing_polygon);
    const alignedStanding = buildNonOverlappingStandingPolygon(alignedPlay, otherStanding, 1 + standingMargin / 100);

    const updated = config.tables.map(t =>
      t.table_id === selectedTable
        ? { ...t, play_polygon: alignedPlay, standing_polygon: alignedStanding }
        : t,
    );
    setConfig({ ...config, tables: updated });
    setSelectedVertex(null);
    setNotice(`Đã căn phẳng phối cảnh đối xứng cho Bàn ${selectedTable} (giữ nguyên độ nghiêng 3D của camera).`);
  };

  const getLoupeStyle = (): React.CSSProperties => {
    const bgSrc =
      useLiveStream && active
        ? `/api/camera/stream?annotated=false&t=${previewKey}`
        : (autoPreviewUrl ?? `/api/calibration/preview?t=${previewKey}`);
    return {
      backgroundImage: `url(${bgSrc})`,
      backgroundSize: `${VIEW_WIDTH * 3.5}px ${VIEW_HEIGHT * 3.5}px`,
      backgroundPosition: `${-(cursorCoords?.[0] ?? 0.5) * VIEW_WIDTH * 3.5 + 70}px ${-(cursorCoords?.[1] ?? 0.5) * VIEW_HEIGHT * 3.5 + 70}px`,
    };
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const res = await request<CalibrationResponse>('/calibration/zones', config);
      setConfig(res.config);
      setSavedConfig(res.config);
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
    return (
      <div className="detail-panel roi-loading-panel">
        <div className="spinner-lg" />
        <p>Đang tải cấu hình ROI từ hệ thống…</p>
      </div>
    );
  }

  const activePoints = currentTable ? getPoints(currentTable, activeMode) : [];

  return (
    <div className="roi-editor-container">
      <div className="section-heading">
        <div>
          <h2>Công cụ Hiệu chuẩn Vùng Bàn (ROI Editor)</h2>
          <p>
            Căn chỉnh đa giác mặt nỉ (Play) và vùng đứng (Standing) cho tối đa {maxTables} bàn. Kéo rê chuột vào thân đa giác để di chuyển cả bàn.
          </p>
        </div>
        <div className="roi-header-actions">
          <button
            type="button"
            className="button roi-auto-detect-btn"
            disabled={autoDetecting || saving || !config}
            onClick={handleAutoDetect}
            title="Phân tích mặt nỉ và đường biên từ khung hình camera/video hiện tại bằng AI & OpenCV local"
          >
            {autoDetecting ? (
              <>
                <span className="spinner-sm" />
                Đang nhận diện bàn…
              </>
            ) : (
              '🪄 Tự nhận diện bàn'
            )}
          </button>
          <button
            type="button"
            className={`button ${useLiveStream ? 'primary' : 'subtle'}`}
            disabled={autoDetecting}
            onClick={() => {
              setAutoPreviewUrl(null);
              setUseLiveStream(!useLiveStream);
            }}
            title="Bật stream trực tiếp từ camera làm ảnh nền hiệu chuẩn"
          >
            {useLiveStream ? '● Stream camera trực tiếp' : 'Ảnh nền tĩnh'}
          </button>
          <button
            type="button"
            className="button subtle"
            disabled={autoDetecting}
            onClick={() => {
              setAutoPreviewUrl(null);
              setPreviewKey(Date.now());
              setNotice('Đã chụp frame mới từ camera');
            }}
          >
            Chụp lại ảnh nền
          </button>
          <button type="button" className="button primary" disabled={saving || autoDetecting || !config} onClick={handleSave}>
            {saving ? (
              <>
                <span className="spinner-sm" />
                Đang lưu…
              </>
            ) : (
              'Lưu cấu hình ROI'
            )}
          </button>
        </div>
      </div>

      <p className="roi-card-hint">
        Tự nhận diện dùng màu mặt nỉ xanh lá/xanh dương và hình học ảnh. Mặt bàn bị phủ hoặc che nhiều có thể bị bỏ sót; kiểm tra vùng đứng trước khi lưu.
      </p>

      {error && (
        <div className="message error" role="alert">
          {error}
          <button type="button" onClick={() => setError('')} aria-label="Đóng">×</button>
        </div>
      )}
      {notice && (
        <div className="message success" role="status">
          {notice}
          <button type="button" onClick={() => setNotice('')} aria-label="Đóng">×</button>
        </div>
      )}

      {hasUnsavedChanges && (
        <div className="message warning" role="status">
          ROI đang chỉnh chưa được lưu. Trang Camera trực tiếp vẫn hiển thị ROI đã lưu; bấm “Lưu cấu hình ROI” để áp dụng.
        </div>
      )}

      {autoWarnings.length > 0 && (
        <div className="message warning" role="status">
          <ul>{autoWarnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
        </div>
      )}

      {displayedOverlaps.length > 0 && (
        <div className="message warning roi-overlap-alert" role="alert">
          <div>
            <strong>Cảnh báo chồng lấn vùng đứng (AMBIGUOUS):</strong>
            <ul>
              {displayedOverlaps.map((o, idx) => (
                <li key={`${o.table_a}-${o.table_b}-${idx}`}>{o.message}</li>
              ))}
            </ul>
            <p className="roi-overlap-explain">
              Người đứng ở vùng giao nhau giữa hai bàn sẽ bị đánh dấu AMBIGUOUS và hệ thống không tự mở bàn.
            </p>
          </div>
        </div>
      )}

      <div className="roi-table-bar">
        <span className="roi-table-bar-label">BÀN HIỆU CHUẨN:</span>
        {tableIds.map(id => {
          const zone = config?.tables.find(t => t.table_id === id);
          return (
            <button
              key={id}
              type="button"
              className={`button roi-table-btn ${selectedTable === id ? 'primary' : 'subtle'}`}
              onClick={() => {
                setSelectedTable(id);
                setSelectedVertex(null);
              }}
            >
              <span>Bàn {id.toString().padStart(2, '0')}</span>
              {!zone && <span className="roi-table-tag missing">Chưa hiệu chuẩn</span>}
              {zone && !zone.enabled && <span className="roi-table-tag disabled">Đang tắt</span>}
            </button>
          );
        })}
        <button
          type="button"
          className="button subtle roi-add-btn"
          disabled={!config || nextMissingId === null}
          onClick={() => {
            if (nextMissingId !== null) handleAddTable(nextMissingId);
          }}
          title={nextMissingId === null ? `Đã đủ tối đa ${maxTables} bàn` : `Thêm vùng ROI cho Bàn ${nextMissingId}`}
        >
          + Thêm bàn
        </button>
        <button
          type="button"
          className="button danger"
          disabled={!currentTable || saving}
          onClick={() => handleDeleteTable(selectedTable)}
          title="Xóa vùng mặt nỉ và vùng đứng của bàn đang chọn; bấm Lưu để áp dụng"
        >
          Xóa ROI Bàn {selectedTable.toString().padStart(2, '0')}
        </button>
        <label className="roi-hide-others">
          <input
            type="checkbox"
            checked={hideOtherTables}
            onChange={e => setHideOtherTables(e.target.checked)}
          />
          Chỉ hiện bàn đang chọn
        </label>
      </div>

      <div className="roi-layout">
        {isCornerMode && (
          <div className="roi-corner-banner" role="status" style={{ gridColumn: '1 / -1' }}>
            <div className="roi-corner-banner-content">
              <span className="roi-corner-badge">BƯỚC {cornerPoints.length + 1}/4</span>
              <strong>{CORNER_NAMES[cornerPoints.length]}</strong>
              <span className="roi-corner-hint">(Click chuột vào góc mép nỉ trên ảnh để định vị góc này)</span>
            </div>
            <button
              type="button"
              className="button subtle roi-corner-cancel-btn"
              onClick={() => {
                setIsCornerMode(false);
                setCornerPoints([]);
                setNotice('Đã hủy chế độ chấm 4 góc.');
              }}
            >
              ✕ Hủy chấm góc (ESC)
            </button>
          </div>
        )}
        <div className="roi-viewport">
          {useLiveStream && active ? (
            <img
              src={`/api/camera/stream?annotated=false&t=${previewKey}`}
              alt="Camera Stream Live"
              onLoad={handleImageLoad}
              className="roi-bg-img"
            />
          ) : (
            <img
              src={autoPreviewUrl ?? `/api/calibration/preview?t=${previewKey}`}
              alt={autoPreviewUrl ? 'Khung hình dùng để tự nhận diện ROI' : 'Camera Calibration Preview'}
              onLoad={handleImageLoad}
              className="roi-bg-img"
            />
          )}

          {autoDetecting && (
            <div className="roi-ai-scan-overlay" role="status" aria-live="polite">
              <div className="roi-ai-scan-beam" />
              <div className="roi-ai-scan-badge">
                <span className="spinner-sm" />
                <span>AI YOLOv8-seg đang quét phân đoạn bàn bi-a…</span>
              </div>
            </div>
          )}

          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            preserveAspectRatio="none"
            className="roi-svg-layer"
            style={{
              cursor: isCornerMode ? 'crosshair' : !currentTable ? 'default' : isTranslating ? 'grabbing' : toolMode === 'add' ? 'crosshair' : 'default',
            }}
            onClick={handleSvgClick}
            onMouseMove={handleSvgMouseMove}
            onMouseUp={handleSvgMouseUp}
            onMouseLeave={handleSvgMouseLeave}
          >
            {isCornerMode && (
              <g className="roi-corner-preview-group">
                {cornerPoints.length >= 2 && (
                  <polyline
                    points={cornerPoints.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                    fill="none"
                    stroke="#0284c7"
                    strokeWidth={2.5}
                  />
                )}
                {cornerPoints.length > 0 && cursorCoords && (
                  <line
                    x1={cornerPoints[cornerPoints.length - 1][0] * VIEW_WIDTH}
                    y1={cornerPoints[cornerPoints.length - 1][1] * VIEW_HEIGHT}
                    x2={cursorCoords[0] * VIEW_WIDTH}
                    y2={cursorCoords[1] * VIEW_HEIGHT}
                    stroke="#f59e0b"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                  />
                )}
                {cornerPoints.map(([x, y], idx) => (
                  <g key={`corner-pt-${idx}`}>
                    <circle
                      cx={x * VIEW_WIDTH}
                      cy={y * VIEW_HEIGHT}
                      r={10}
                      fill="#0284c7"
                      stroke="#ffffff"
                      strokeWidth={2.5}
                    />
                    <text
                      x={x * VIEW_WIDTH}
                      y={y * VIEW_HEIGHT + 4}
                      fill="#ffffff"
                      fontSize="11"
                      fontWeight="bold"
                      textAnchor="middle"
                    >
                      {idx + 1}
                    </text>
                  </g>
                ))}
              </g>
            )}

            {!hideOtherTables &&
              config?.tables.map(table => {
                if (table.table_id === selectedTable) return null;
                const playPts = table.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
                const standPts = table.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ');
                const muted = !table.enabled;
                return (
                  <g
                    key={table.table_id}
                    opacity={muted ? 0.3 : 0.45}
                    style={{
                      cursor: isCornerMode ? 'crosshair' : 'pointer',
                      pointerEvents: isCornerMode ? 'none' : 'auto',
                    }}
                    onClick={() => !isCornerMode && setSelectedTable(table.table_id)}
                  >
                    <polygon
                      points={standPts}
                      fill={muted ? '#94a3b8' : '#f59e0b'}
                      fillOpacity={0.08}
                      stroke={muted ? '#64748b' : '#f59e0b'}
                      strokeWidth={1}
                      strokeDasharray="3 3"
                    />
                    <polygon
                      points={playPts}
                      fill={muted ? '#94a3b8' : '#10b981'}
                      fillOpacity={0.15}
                      stroke={muted ? '#64748b' : '#10b981'}
                      strokeWidth={1.5}
                    />
                    <text
                      x={table.play_polygon[0][0] * VIEW_WIDTH + 8}
                      y={table.play_polygon[0][1] * VIEW_HEIGHT + 18}
                      fill={muted ? '#475569' : '#5d6d63'}
                      fontSize="12"
                      fontWeight="bold"
                    >
                      Bàn {table.table_id}{muted ? ' (Tắt)' : ''}
                    </text>
                  </g>
                );
              })}

            {currentTable && (
              <g key={`selected-${currentTable.table_id}`} opacity={currentTable.enabled ? 1 : 0.6}>
                <polygon
                  points={currentTable.standing_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill={currentTable.enabled ? '#f59e0b' : '#94a3b8'}
                  fillOpacity={activeMode === 'standing' ? 0.28 : 0.08}
                  stroke={currentTable.enabled ? '#f59e0b' : '#64748b'}
                  strokeWidth={activeMode === 'standing' ? 2.5 : 1}
                  strokeDasharray={activeMode === 'standing' && currentTable.enabled ? undefined : '4 4'}
                  style={{
                    cursor: isCornerMode ? 'crosshair' : activeMode === 'standing' ? (isTranslating ? 'grabbing' : 'grab') : 'pointer',
                    pointerEvents: isCornerMode ? 'none' : 'auto',
                  }}
                  onMouseDown={!isCornerMode && activeMode === 'standing' ? handlePolygonMouseDown : undefined}
                />

                <polygon
                  points={currentTable.play_polygon.map(([x, y]) => `${x * VIEW_WIDTH},${y * VIEW_HEIGHT}`).join(' ')}
                  fill={currentTable.enabled ? '#10b981' : '#94a3b8'}
                  fillOpacity={activeMode === 'play' ? 0.35 : 0.15}
                  stroke={currentTable.enabled ? '#10b981' : '#64748b'}
                  strokeWidth={activeMode === 'play' ? 3 : 1.5}
                  style={{
                    cursor: isCornerMode ? 'crosshair' : activeMode === 'play' ? (isTranslating ? 'grabbing' : 'grab') : 'pointer',
                    pointerEvents: isCornerMode ? 'none' : 'auto',
                  }}
                  onMouseDown={!isCornerMode && activeMode === 'play' ? handlePolygonMouseDown : undefined}
                />

                <text
                  x={currentTable.play_polygon[0][0] * VIEW_WIDTH + 8}
                  y={currentTable.play_polygon[0][1] * VIEW_HEIGHT + 20}
                  fill="#ffffff"
                  fontSize="13"
                  fontWeight="bold"
                  filter="drop-shadow(0px 1px 2px rgba(0,0,0,0.8))"
                  style={{ pointerEvents: 'none' }}
                >
                  BÀN {currentTable.table_id.toString().padStart(2, '0')}
                  {!currentTable.enabled ? ' (TẠM TẮT)' : ''}
                  {isTranslating ? ' (Đang di chuyển…)' : ''}
                </text>

                {!isCornerMode &&
                  activePoints.map(([x, y], idx) => {
                    const px = x * VIEW_WIDTH;
                    const py = y * VIEW_HEIGHT;
                    const isHovered = draggingIdx === idx;
                    const isSelected = selectedVertex === idx;
                    const color = !currentTable.enabled ? '#64748b' : activeMode === 'play' ? '#047857' : '#f59e0b';
                    return (
                      <g key={idx}>
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

          {loupeEnabled && cursorCoords && (
            <div
              className="roi-loupe"
              style={getLoupeStyle()}
            >
              <div className="roi-loupe-crosshair-h" />
              <div className="roi-loupe-crosshair-v" />
              <div className="roi-loupe-coord">
                X: {(cursorCoords[0] * 100).toFixed(1)}% | Y: {(cursorCoords[1] * 100).toFixed(1)}%
              </div>
            </div>
          )}
        </div>

        <div className="roi-controls">
          {!currentTable ? (
            <div className="roi-card roi-empty-table">
              <p className="roi-card-title">BÀN {selectedTable.toString().padStart(2, '0')} · CHƯA HIỆU CHUẨN</p>
              <p className="roi-card-hint">
                Bàn này có trong danh sách tính tiền nhưng chưa có vùng ROI, nên chưa nhận tín hiệu AI từ camera.
              </p>
              <button
                type="button"
                className="button primary full-width"
                onClick={() => handleAddTable(selectedTable)}
              >
                + Tạo vùng ROI cho Bàn {selectedTable.toString().padStart(2, '0')}
              </button>
            </div>
          ) : (
            <>
              <div className="roi-card">
                <p className="roi-card-title">QUẢN LÝ BÀN {currentTable.table_id.toString().padStart(2, '0')}</p>
                <label className="roi-toggle-label">
                  <input
                    type="checkbox"
                    checked={currentTable.enabled}
                    onChange={e => handleToggleEnabled(currentTable.table_id, e.target.checked)}
                  />
                  <span>Theo dõi AI cho Bàn {currentTable.table_id.toString().padStart(2, '0')}</span>
                </label>
                <p className="roi-card-hint">
                  Tắt khi bàn phủ vải hoặc không dùng để bỏ qua nhận diện AI cho bàn này.
                </p>
              </div>

              <div className="roi-card">
                <p className="roi-card-title">CHỌN LỚP ĐIỀU CHỈNH</p>
                <div className="roi-btn-grid">
                  <button
                    type="button"
                    className={`button ${activeMode === 'play' ? 'primary' : 'subtle'}`}
                    onClick={() => {
                      setActiveMode('play');
                      setSelectedVertex(null);
                    }}
                  >
                    Mặt nỉ ({currentTable.play_polygon.length})
                  </button>
                  <button
                    type="button"
                    className={`button ${activeMode === 'standing' ? 'primary' : 'subtle'}`}
                    onClick={() => {
                      setActiveMode('standing');
                      setSelectedVertex(null);
                    }}
                  >
                    Vùng đứng ({currentTable.standing_polygon.length})
                  </button>
                </div>

                <p className="roi-card-title">CHẾ ĐỘ THAO TÁC</p>
                <div className="roi-btn-grid">
                  <button
                    type="button"
                    className={`button ${toolMode === 'select' ? 'primary' : 'subtle'}`}
                    onClick={() => setToolMode('select')}
                    title="Kéo đỉnh hoặc kéo cả bàn"
                  >
                    Chọn &amp; Kéo bàn
                  </button>
                  <button
                    type="button"
                    className={`button ${toolMode === 'add' ? 'primary' : 'subtle'}`}
                    onClick={() => setToolMode('add')}
                    title="Click lên ảnh để thêm đỉnh mới"
                  >
                    + Thêm đỉnh
                  </button>
                </div>

                {activeMode === 'play' && (
                  <label className="roi-check-label">
                    <input
                      type="checkbox"
                      checked={syncStanding}
                      onChange={e => setSyncStanding(e.target.checked)}
                    />
                    Kéo cả vùng đứng khi di chuyển mặt nỉ
                  </label>
                )}
                <label className="roi-check-label">
                  <input
                    type="checkbox"
                    checked={loupeEnabled}
                    onChange={e => setLoupeEnabled(e.target.checked)}
                  />
                  Bật kính lúp phóng đại góc (3.5×)
                </label>
              </div>

              <div className="roi-card">
                <p className="roi-card-title">CÔNG CỤ CĂN NHANH &amp; TỰ ĐỘNG HÓA</p>
                <div className="roi-preset-stack">
                  <button
                    type="button"
                    className={`button full-width ${isCornerMode ? 'primary' : 'roi-btn-highlight'}`}
                    onClick={handleStartCornerMode}
                    title="Click 4 lần vào 4 góc mép nỉ để vẽ lại hình bàn chuẩn theo góc phối cảnh"
                  >
                    {isCornerMode ? 'Đang chờ click 4 góc…' : '🎯 Chấm 4 góc vẽ lại bàn này'}
                  </button>
                  <button
                    type="button"
                    className="button subtle full-width"
                    onClick={handleAlignPerspective}
                    title="Căn phẳng đối xứng 4 góc bàn theo phối cảnh 3D (giữ nguyên độ nghiêng của camera)"
                  >
                    📐 Căn chuẩn phối cảnh (Perspective)
                  </button>
                  <div className="roi-slider-container">
                    <div className="roi-slider-label">
                      <span>Độ rộng vùng đứng:</span>
                      <span>+{standingMargin}%</span>
                    </div>
                    <input
                      type="range"
                      min={15}
                      max={60}
                      step={1}
                      value={standingMargin}
                      onChange={e => handleStandingMarginChange(Number(e.target.value))}
                      className="roi-slider"
                      title="Kéo để điều chỉnh khoảng cách vùng đứng xung quanh bàn"
                    />
                  </div>
                  <button type="button" className="button subtle full-width" onClick={handleOptimizeStandingZones}>
                    🛡️ Tối ưu toàn bộ vùng đứng (0 chồng lấn)
                  </button>
                  <button type="button" className="button subtle full-width" onClick={createStandardRectangle}>
                    Tạo hình chữ nhật chuẩn (4 đỉnh)
                  </button>
                  <button type="button" className="button subtle full-width" onClick={generateStandingFromPlay}>
                    Sinh vùng đứng bao quanh tự động
                  </button>
                  <div className="roi-btn-grid">
                    <button type="button" className="button subtle" onClick={() => scalePolygon(1.1)}>
                      Mở rộng +10%
                    </button>
                    <button type="button" className="button subtle" onClick={() => scalePolygon(0.9)}>
                      Thu nhỏ -10%
                    </button>
                  </div>
                  {selectedVertex !== null && (
                    <button type="button" className="button danger full-width" onClick={deleteSelectedVertex}>
                      Xóa đỉnh #{selectedVertex + 1} đang chọn
                    </button>
                  )}
                  <button type="button" className="button subtle full-width roi-reset-btn" onClick={resetToDefault}>
                    Khôi phục mặc định ban đầu
                  </button>
                </div>
              </div>
            </>
          )}

          <div className="roi-card">
            <p className="roi-card-title">MẸO THAO TÁC TIỆN LỢI</p>
            <ul className="roi-tips-list">
              <li><strong>Tự nhận diện bàn:</strong> Bấm nút <em>&ldquo;🪄 Tự nhận diện bàn&rdquo;</em> ở thanh trên cùng để AI tự quét đề xuất vùng bàn trên khung hình hiện tại.</li>
              <li><strong>Kính lúp góc:</strong> Rê chuột vào góc bàn để xem phóng to 3.5× căn mép nỉ chuẩn từng pixel.</li>
              <li><strong>Di chuyển cả bàn:</strong> Bấm giữ chuột vào <em>lòng đa giác</em> rồi kéo rê.</li>
              <li><strong>Di chuyển đỉnh:</strong> Bấm giữ chuột vào <em>điểm tròn</em> rồi kéo.</li>
              <li><strong>Tối ưu vùng đứng:</strong> Bấm <em>&ldquo;Tối ưu toàn bộ vùng đứng&rdquo;</em> để tự động khử chồng lấn AMBIGUOUS.</li>
              <li><strong>Xóa đỉnh:</strong> Bấm vào đỉnh rồi nhấn phím <code>Delete</code> hoặc nút xóa.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
