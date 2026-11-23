export type ActivityState = 'PLAYING' | 'NOT_PLAYING' | 'UNKNOWN';
export type Session = {
  id: string; table_id: number; started_at: string; ended_at: string | null;
  status: 'ACTIVE' | 'PAID'; hourly_rate_snapshot: number; total_amount: number | null;
  trigger_source: string; evidence_source: string | null;
  elapsed_seconds: number; billable_minutes: number; amount_vnd: number;
};
export type Table = {
  id: number; name: string; status: string; hourly_rate: number; session: Session | null;
  candidate_seconds: number; cooldown_remaining: number; evidence_stale: boolean;
  ai_activity?: ActivityState; ai_paused?: boolean;
  roi_calibrated?: boolean; roi_enabled?: boolean;
  unbilled_playing_seconds?: number; unbilled_alert?: boolean;
  playing_since?: string | null;
};
export type DetectionEvent = {
  id: string; table_id: number; event_type: string; confidence: number; timestamp: string;
  source: string; state: string; reason: string; activity_state?: string;
};
export type UnbilledAlert = {
  table_id: number; name: string; unbilled_playing_seconds: number; playing_since: string | null;
};
export type Snapshot = {
  type: 'snapshot'; server_time: string; timezone: string; mode: string;
  simulation_enabled: boolean; auto_open_enabled: boolean; camera_ready: boolean;
  camera_status?: string;
  model_status: {
    person: { name: string; loaded: boolean; backend: string };
    cue: { name: string; loaded: boolean; backend: string; validated: boolean };
  };
  cue_detector_ready: boolean; decision_config: {
    policy: string; presence_seconds: number; confidence_enter: number; confidence_exit: number;
    max_observation_gap_seconds: number; absence_grace_seconds: number;
    cooldown_seconds: number; cue_confidence: number;
    unbilled_alert_seconds?: number; playing_hold_grace_seconds?: number;
  };
  tables: Table[]; events: DetectionEvent[]; active_count: number;
  revenue_vnd: number; running_amount_vnd: number;
  unbilled_alerts?: UnbilledAlert[];
};
export type Observation = {
  event_id: string; table_id: number; present: boolean; confidence: number; ambiguous: boolean;
  activity_state?: ActivityState;
};

export type VideoFileItem = {
  filename: string;
  size_bytes: number;
  active: boolean;
};

export type VideoListResponse = {
  videos: VideoFileItem[];
  runner_running: boolean;
  runner_status: string;
  models: {
    pose: boolean;
    person: boolean;
    cue: boolean;
  };
};

export type TableEvalStats = {
  PLAYING_seconds: number;
  NOT_PLAYING_seconds: number;
  UNKNOWN_seconds: number;
  first_needs_confirmation_at_s: number | null;
  first_unbilled_alert_at_s: number | null;
  final_state: string;
  unbilled_alert_triggered: boolean;
};

export type VideoEvaluationReport = {
  video_path: string;
  video_fps: number;
  sampled_fps: number;
  processed_frames: number;
  video_duration_seconds: number;
  wall_seconds: number;
  processing_fps: number;
  person_pose_model_ready: boolean;
  person_pose_backend: string;
  cue_model_ready: boolean;
  cue_backend: string;
  unbilled_alert_threshold_seconds: number;
  tables: Record<string, TableEvalStats>;
};

export type VideoUploadResponse = {
  filename: string;
  size_bytes: number;
  live_started: boolean;
  runner_status: string;
  evaluation: VideoEvaluationReport | null;
};

export type DatasetManifest = {
  dataset_id: string;
  split_counts: { train: number; val: number; test: number };
  total_images: number;
  dataset_yaml: string;
};

export type TableZoneConfig = {
  table_id: number;
  enabled: boolean;
  play_polygon: [number, number][];
  standing_polygon: [number, number][];
};

export type ZoneOverlapWarning = {
  table_a: number;
  table_b: number;
  message: string;
};

export type CalibrationConfig = {
  camera_id: string;
  calibration_status: string;
  coordinate_system: string;
  tables: TableZoneConfig[];
};

export type CalibrationResponse = {
  config: CalibrationConfig;
  overlaps: ZoneOverlapWarning[];
  message?: string;
  detected_count?: number;
};

export type AutoCalibrationResponse = CalibrationResponse & {
  method: string;
  requires_review: true;
  detected_count: number;
  updated_table_ids: number[];
  warnings: string[];
  preview_data_url: string;
  captured_at: string;
};

export type DecisionSettings = {
  policy: 'PERSON_ONLY' | 'PERSON_AND_CUE' | 'POSE_AND_CUE' | 'SMART_STANCE';
  presence_seconds: number; confidence_enter: number; confidence_exit: number;
  max_observation_gap_seconds: number; absence_grace_seconds: number; cooldown_seconds: number;
  cue_confidence: number; unbilled_alert_seconds: number; playing_hold_grace_seconds: number;
};

export type RuntimeSettings = {
  decision: DecisionSettings; decision_defaults: DecisionSettings;
  auto_open: boolean; camera_source: string; camera_source_default: string;
  overridden: string[]; persisted: boolean;
};
