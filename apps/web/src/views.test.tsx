import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  RoiEditor,
  addTableZoneToConfig,
  alignPerspectivePolygon,
  buildNonOverlappingStandingPolygon,
  detectLocalOverlaps,
  getNextUncalibratedTableId,
  polygonsOverlap,
  removeTableZoneFromConfig,
  shouldRefreshRoiPreview,
  toggleTableEnabledInConfig,
} from './RoiEditor';
import { money } from './format';
import { HistoryView } from './views/HistoryView';
import { LabView } from './views/LabView';
import { LiveView } from './views/LiveView';
import { SystemView } from './views/SystemView';
import { TablesView } from './views/TablesView';
import type { CalibrationConfig, Session, Snapshot } from './types';

function makeSnapshot(): Snapshot {
  return {
    type: 'snapshot',
    server_time: '2026-11-18T11:30:00Z',
    timezone: 'Asia/Ho_Chi_Minh',
    mode: 'SIMULATED',
    simulation_enabled: true,
    auto_open_enabled: false,
    camera_ready: false,
    camera_status: 'Đã dừng',
    model_status: {
      person: { name: 'yolov8n-pose', loaded: false, backend: 'none' },
      cue: { name: 'yolov8n-cue', loaded: false, backend: 'none', validated: false },
    },
    cue_detector_ready: false,
    decision_config: {
      policy: 'STAFF_CONFIRMATION',
      presence_seconds: 5,
      confidence_enter: 0.75,
      confidence_exit: 0.5,
      max_observation_gap_seconds: 3,
      absence_grace_seconds: 5,
      cooldown_seconds: 15,
      cue_confidence: 0.5,
      unbilled_alert_seconds: 300,
    },
    tables: [
      {
        id: 1,
        name: 'Bàn 01',
        status: 'NEEDS_CONFIRMATION',
        hourly_rate: 60000,
        session: null,
        candidate_seconds: 6,
        cooldown_remaining: 0,
        evidence_stale: false,
        ai_activity: 'PLAYING',
        unbilled_playing_seconds: 320,
        unbilled_alert: true,
      },
      {
        id: 2,
        name: 'Bàn 02',
        status: 'ACTIVE',
        hourly_rate: 60000,
        session: {
          id: 'sess-0002-abcd',
          table_id: 2,
          started_at: '2026-11-18T10:30:00Z',
          ended_at: null,
          status: 'ACTIVE',
          hourly_rate_snapshot: 60000,
          total_amount: null,
          trigger_source: 'STAFF_CONFIRMATION',
          evidence_source: 'SIMULATED',
          elapsed_seconds: 3600,
          billable_minutes: 60,
          amount_vnd: 60000,
        },
        candidate_seconds: 0,
        cooldown_remaining: 0,
        evidence_stale: false,
        ai_activity: 'PLAYING',
      },
    ],
    events: [
      {
        id: 'evt-1',
        table_id: 1,
        event_type: 'PRESENCE',
        confidence: 0.91,
        timestamp: '2026-11-18T11:29:50Z',
        source: 'SIMULATED',
        state: 'NEEDS_CONFIRMATION',
        reason: 'UNBILLED_PLAY_OVER_5M',
      },
      {
        id: 'evt-2',
        table_id: 2,
        event_type: 'PRESENCE',
        confidence: 0.95,
        timestamp: '2026-11-18T11:29:55Z',
        source: 'SIMULATED',
        state: 'ACTIVE',
        reason: 'SESSION_ACTIVE',
      },
    ],
    active_count: 1,
    revenue_vnd: 185000,
    running_amount_vnd: 60000,
  };
}

describe('reorganized UI views', () => {
  it('TablesView renders only alert banner and table cards, expanding at most one card inline', () => {
    const data = makeSnapshot();
    const collapsedHtml = renderToStaticMarkup(
      <TablesView
        data={data}
        expandedTableId={null}
        onToggleTable={vi.fn()}
        locked={false}
        onOpenTable={vi.fn()}
        onShowCheckout={vi.fn()}
        onViewCamera={vi.fn()}
      />,
    );

    expect(collapsedHtml).toContain('alert-banner-5m');
    expect(collapsedHtml).toContain('Mở Bàn 01');
    expect(collapsedHtml).toContain('Tính bù giờ AI');
    expect(collapsedHtml).not.toContain('table-card-detail');
    expect(collapsedHtml).not.toContain('stats-grid');
    expect(collapsedHtml).not.toContain('simulation-panel');
    expect(collapsedHtml).not.toContain('demo-banner');

    const expandedHtml = renderToStaticMarkup(
      <TablesView
        data={data}
        expandedTableId={2}
        onToggleTable={vi.fn()}
        locked={false}
        onOpenTable={vi.fn()}
        onShowCheckout={vi.fn()}
        onViewCamera={vi.fn()}
      />,
    );

    const detailMatches = expandedHtml.match(/class="table-card-detail"/g) ?? [];
    expect(detailMatches).toHaveLength(1);
    expect(expandedHtml).toContain('BẮT ĐẦU PHIÊN');
    expect(expandedHtml).toContain('NGUỒN MỞ BÀN');
    expect(expandedHtml).toContain('QUY TẮC TÍNH TIỀN');
    expect(expandedHtml).toContain('Nhân viên xác nhận');
  });

  it('TablesView alerts when AI sees play awaiting confirmation, offers camera, and marks paused tables', () => {
    const data = makeSnapshot();
    data.tables = data.tables.map(item => item.session
      ? { ...item, ai_paused: true }
      : { ...item, status: 'NEEDS_CONFIRMATION', unbilled_alert: false });
    const html = renderToStaticMarkup(
      <TablesView data={data} expandedTableId={null} onToggleTable={vi.fn()} locked={false}
        onOpenTable={vi.fn()} onShowCheckout={vi.fn()} onViewCamera={vi.fn()} />,
    );
    expect(html).toContain('alert-banner-confirm');
    expect(html).toContain('Xem camera');
    expect(html).toContain('Xác nhận mở');
    expect(html).toContain('Tính bù giờ AI');
    expect(html).toContain('AI tạm dừng');
  });

  it('LabView pauses MJPEG stream preview when tab is inactive', () => {
    const data = makeSnapshot();
    const hiddenHtml = renderToStaticMarkup(
      <LabView
        data={data}
        active={false}
        online={true}
        locked={false}
        simTable={1}
        onChangeSimTable={vi.fn()}
        simulating={false}
        onStartSimulation={vi.fn()}
        onStopSimulation={vi.fn()}
        onReplayLastEvent={vi.fn()}
        hasLastEvent={false}
        ambiguous={false}
        onChangeAmbiguous={vi.fn()}
        confidence={0.9}
        onChangeConfidence={vi.fn()}
        activityState="PLAYING"
        onChangeActivityState={vi.fn()}
        logTableId={1}
        onChangeLogTableId={vi.fn()}
        onStartCamera={vi.fn()}
        onStopCamera={vi.fn()}
        onOpenLiveTab={vi.fn()}
        onJumpCalibration={vi.fn()}
        onNotice={vi.fn()}
        onError={vi.fn()}
      />,
    );
    expect(hiddenHtml).not.toContain('/api/camera/stream');
    expect(hiddenHtml).toContain('Tạm dừng luồng xem nhanh khi ẩn tab');
  });

  it('LabView shows mode banner, artificial data simulator, camera mini preview, and table-scoped log selector', () => {
    const data = makeSnapshot();
    const html = renderToStaticMarkup(
      <LabView
        data={data}
        online={true}
        locked={false}
        simTable={1}
        onChangeSimTable={vi.fn()}
        simulating={false}
        onStartSimulation={vi.fn()}
        onStopSimulation={vi.fn()}
        onReplayLastEvent={vi.fn()}
        hasLastEvent={false}
        ambiguous={false}
        onChangeAmbiguous={vi.fn()}
        confidence={0.9}
        onChangeConfidence={vi.fn()}
        activityState="PLAYING"
        onChangeActivityState={vi.fn()}
        logTableId={2}
        onChangeLogTableId={vi.fn()}
        onStartCamera={vi.fn()}
        onStopCamera={vi.fn()}
        onOpenLiveTab={vi.fn()}
        onJumpCalibration={vi.fn()}
        onNotice={vi.fn()}
        onError={vi.fn()}
      />,
    );

    expect(html).toContain('demo-banner');
    expect(html).toContain('DỮ LIỆU NHÂN TẠO');
    expect(html).toContain('/api/camera/stream');
    expect(html).toContain('aria-label="Chọn bàn xem nhật ký"');
    expect(html).toContain('Giữ nguyên phiên đang chơi');
    expect(html).not.toContain('Cảnh báo: chơi quá 5 phút chưa mở bàn');
  });

  it('LiveView renders camera stream, legend, video panel, and status without inline layout styles', () => {
    const data = makeSnapshot();
    const html = renderToStaticMarkup(
      <LiveView
        data={data}
        locked={false}
        onStartCamera={vi.fn()}
        onStopCamera={vi.fn()}
        onJumpCalibration={vi.fn()}
        onNotice={vi.fn()}
        onError={vi.fn()}
      />,
    );

    expect(html).toContain('class="live-camera-panel"');
    expect(html).toContain('/api/camera/stream');
    expect(html).toContain('CHÚ GIẢI TRỰC QUAN');
    expect(html).toContain('Trạng thái camera và model');
    expect(html).toContain('video-automation-panel');
    expect(html).not.toContain('<section class="live-camera-panel" style=');
    expect(html).not.toContain('<div class="live-card" style=');
    expect(html).not.toContain('<dl class="system-grid live-status-grid" style=');
  });

  it('LiveView distinguishes the fast preset from missing cue weights', () => {
    const data = makeSnapshot();
    data.model_status.cue = { ...data.model_status.cue, loaded: false, backend: 'DISABLED' };
    const html = renderToStaticMarkup(
      <LiveView data={data} locked={false} onStartCamera={vi.fn()} onStopCamera={vi.fn()}
        onJumpCalibration={vi.fn()} onNotice={vi.fn()} onError={vi.fn()} />,
    );
    expect(html).toContain('Đã tắt để ưu tiên FPS (chế độ nhanh)');
    expect(html).not.toContain('Chưa nạp weights gậy');
  });

  it('HistoryView shows settled demo revenue from backend snapshot', () => {
    const data = makeSnapshot();
    const paidSession: Session = {
      id: 'sess-paid-01',
      table_id: 1,
      started_at: '2026-11-18T08:00:00Z',
      ended_at: '2026-11-18T09:00:00Z',
      status: 'PAID',
      hourly_rate_snapshot: 60000,
      total_amount: 60000,
      trigger_source: 'STAFF',
      evidence_source: null,
      elapsed_seconds: 3600,
      billable_minutes: 60,
      amount_vnd: 60000,
    };

    const html = renderToStaticMarkup(
      <HistoryView
        data={data}
        history={[paidSession]}
        historyPage={0}
        historyLoading={false}
        onChangePage={vi.fn()}
      />,
    );

    expect(html).toContain('Doanh thu demo đã chốt');
    expect(html).toContain(money(185000));
    expect(html).toContain('Đã thanh toán demo');
  });

  it('SystemView places the 4-metric stats strip at the top above system config', () => {
    const data = makeSnapshot();
    const html = renderToStaticMarkup(<SystemView data={data} />);

    const statsIndex = html.indexOf('class="stats-grid"');
    const panelIndex = html.indexOf('class="system-panel"');
    expect(statsIndex).toBeGreaterThan(-1);
    expect(panelIndex).toBeGreaterThan(statsIndex);
    expect(html).toContain('Bàn đang hoạt động');
    expect(html).toContain('Tiền phiên đang chơi');
    expect(html).toContain('Doanh thu demo đã chốt');
    expect(html).toContain('Chờ nhân viên xác nhận');
    expect(html).toContain('settings-panel');
    expect(html).not.toContain('configs/decision.toml');
  });

  it('TablesView and LiveView warn when a table has no calibrated or enabled AI zone', () => {
    const data = makeSnapshot();
    data.tables[0] = { ...data.tables[0], roi_calibrated: false, roi_enabled: false };
    data.tables[1] = { ...data.tables[1], roi_calibrated: true, roi_enabled: false };

    const tablesHtml = renderToStaticMarkup(
      <TablesView
        data={data}
        expandedTableId={null}
        onToggleTable={vi.fn()}
        locked={false}
        onOpenTable={vi.fn()}
        onShowCheckout={vi.fn()}
        onViewCamera={vi.fn()}
      />,
    );
    expect(tablesHtml).toContain('Chưa có vùng AI');
    expect(tablesHtml).toContain('Chưa hiệu chuẩn ROI');
    expect(tablesHtml).toContain('Đang tắt theo dõi ROI');

    const liveHtml = renderToStaticMarkup(
      <LiveView
        data={data}
        locked={false}
        onStartCamera={vi.fn()}
        onStopCamera={vi.fn()}
        onJumpCalibration={vi.fn()}
        onNotice={vi.fn()}
        onError={vi.fn()}
      />,
    );
    expect(liveHtml).toContain('CHƯA CÓ VÙNG AI CHO 2 BÀN');
    expect(liveHtml).toContain('chưa hiệu chuẩn ROI');
    expect(liveHtml).toContain('đang tắt theo dõi');
  });

  it('RoiEditor manages multiple tables: uncalibrated labels, add limit, toggle enabled, delete, and overlap avoidance', () => {
    const baseConfig: CalibrationConfig = {
      camera_id: 'cam-01',
      calibration_status: 'CALIBRATED',
      coordinate_system: 'normalized_xy_0_1',
      tables: [
        {
          table_id: 1,
          enabled: true,
          play_polygon: [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
          standing_polygon: [[0.05, 0.05], [0.38, 0.05], [0.38, 0.38], [0.05, 0.38]],
        },
      ],
    };

    const htmlPartial = renderToStaticMarkup(
      <RoiEditor
        tableCount={4}
        initialResponse={{ config: baseConfig, overlaps: [] }}
      />,
    );
    expect(htmlPartial).toContain('Bàn 01');
    expect(htmlPartial).toContain('Bàn 02');
    expect(htmlPartial).toContain('Chưa hiệu chuẩn');
    expect(htmlPartial).toContain('+ Thêm bàn');
    expect(htmlPartial).toContain('Theo dõi AI cho Bàn 01');
    expect(htmlPartial).toContain('Xóa ROI Bàn 01');
    expect(htmlPartial).toContain('Tự nhận diện bàn');

    // Add tables 2, 3, 4 and enforce TABLE_COUNT limit (= 4)
    let cfg = baseConfig;
    for (let next = getNextUncalibratedTableId(cfg.tables, 4); next !== null; next = getNextUncalibratedTableId(cfg.tables, 4)) {
      cfg = addTableZoneToConfig(cfg, next, 4);
    }
    expect(cfg.tables.map(t => t.table_id)).toEqual([1, 2, 3, 4]);
    expect(getNextUncalibratedTableId(cfg.tables, 4)).toBeNull();
    expect(addTableZoneToConfig(cfg, 5, 4).tables).toHaveLength(4);

    // Toggle enabled off & delete table
    cfg = toggleTableEnabledInConfig(cfg, 2, false);
    expect(cfg.tables.find(t => t.table_id === 2)?.enabled).toBe(false);
    const htmlWithDisabled = renderToStaticMarkup(
      <RoiEditor
        tableCount={4}
        initialResponse={{ config: cfg, overlaps: [] }}
      />,
    );
    expect(htmlWithDisabled).toContain('Đang tắt');
    expect(htmlWithDisabled).toContain('disabled=""');

    cfg = removeTableZoneFromConfig(cfg, 3);
    expect(cfg.tables.map(t => t.table_id)).toEqual([1, 2, 4]);

    // Auto-standing generation avoids adjacent table standing polygon when free space exists
    const adjacentPlay: [number, number][] = [[0.1, 0.42], [0.3, 0.42], [0.3, 0.62], [0.1, 0.62]];
    const avoidedStanding = buildNonOverlappingStandingPolygon(
      adjacentPlay,
      [baseConfig.tables[0].standing_polygon],
      1.35,
    );
    expect(polygonsOverlap(avoidedStanding, baseConfig.tables[0].standing_polygon)).toBe(false);

    // Overlap detection reports active overlaps and skips disabled tables
    const overlappingCfg: CalibrationConfig = {
      ...baseConfig,
      tables: [
        baseConfig.tables[0],
        {
          table_id: 2,
          enabled: true,
          play_polygon: [[0.32, 0.1], [0.5, 0.1], [0.5, 0.3], [0.32, 0.3]],
          standing_polygon: [[0.28, 0.05], [0.55, 0.05], [0.55, 0.38], [0.28, 0.38]],
        },
      ],
    };
    const overlaps = detectLocalOverlaps(overlappingCfg.tables);
    expect(overlaps).toHaveLength(1);
    const htmlOverlap = renderToStaticMarkup(
      <RoiEditor
        tableCount={4}
        initialResponse={{ config: overlappingCfg, overlaps }}
      />,
    );
    expect(htmlOverlap).toContain('Cảnh báo chồng lấn vùng đứng (AMBIGUOUS)');
    expect(detectLocalOverlaps(toggleTableEnabledInConfig(overlappingCfg, 2, false).tables)).toHaveLength(0);
  });

  it('alignPerspectivePolygon preserves orientation and creates a symmetric perspective quadrilateral', () => {
    // Slightly skewed trapezoid from perspective camera
    const skewed: [number, number][] = [
      [0.2, 0.2],
      [0.6, 0.22],
      [0.65, 0.45],
      [0.15, 0.43],
    ];
    const aligned = alignPerspectivePolygon(skewed);
    expect(aligned).toHaveLength(4);
    for (const [x, y] of aligned) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(1);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(1);
    }
    // Verify top edge is higher than bottom edge
    expect(aligned[0][1]).toBeLessThan(aligned[3][1]);
    expect(aligned[1][1]).toBeLessThan(aligned[2][1]);
    // Verify left edge is left of right edge
    expect(aligned[0][0]).toBeLessThan(aligned[1][0]);
    expect(aligned[3][0]).toBeLessThan(aligned[2][0]);
  });

  it('renders RoiEditor with 4-corner mode, perspective align, and standing margin controls', () => {
    const baseConfig: CalibrationConfig = {
      camera_id: 'cam_overhead_01',
      calibration_status: 'CALIBRATED',
      coordinate_system: 'NORMALIZED_0_1',
      tables: [
        {
          table_id: 1,
          enabled: true,
          play_polygon: [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
          standing_polygon: [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]],
        },
      ],
    };
    const html = renderToStaticMarkup(
      <RoiEditor tableCount={2} initialResponse={{ config: baseConfig, overlaps: [] }} />,
    );
    expect(html).toContain('Chấm 4 góc vẽ lại bàn này');
    expect(html).toContain('Căn chuẩn phối cảnh (Perspective)');
    expect(html).toContain('Độ rộng vùng đứng:');
    expect(html).toContain('Bật kính lúp phóng đại góc (3.5×)');
  });

  it('shouldRefreshRoiPreview refreshes background when source changes or ROI tab becomes active', () => {
    expect(
      shouldRefreshRoiPreview(
        { active: false, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        { active: false, sourceKey: 'b.mp4|VIDEO_LIVE|1' },
        true,
      ),
    ).toEqual({ clearAutoPreview: true, refreshPreview: false });

    expect(
      shouldRefreshRoiPreview(
        { active: false, sourceKey: 'b.mp4|VIDEO_LIVE|1' },
        { active: true, sourceKey: 'b.mp4|VIDEO_LIVE|1' },
        false,
      ),
    ).toEqual({ clearAutoPreview: false, refreshPreview: true });

    expect(
      shouldRefreshRoiPreview(
        { active: true, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        { active: true, sourceKey: 'b.mp4|VIDEO_LIVE|1' },
        true,
      ),
    ).toEqual({ clearAutoPreview: true, refreshPreview: true });

    expect(
      shouldRefreshRoiPreview(
        { active: false, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        { active: true, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        true,
      ),
    ).toEqual({ clearAutoPreview: false, refreshPreview: false });

    expect(
      shouldRefreshRoiPreview(
        { active: false, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        { active: true, sourceKey: 'a.mp4|VIDEO_LIVE|1' },
        false,
      ),
    ).toEqual({ clearAutoPreview: false, refreshPreview: true });
  });
});
