export type Session = {
  id: string; table_id: number; started_at: string; ended_at: string | null;
  status: 'ACTIVE' | 'PAID'; hourly_rate_snapshot: number; total_amount: number | null;
  trigger_source: string; evidence_source: string | null;
  elapsed_seconds: number; billable_minutes: number; amount_vnd: number;
};
export type Table = {
  id: number; name: string; status: string; hourly_rate: number; session: Session | null;
  candidate_seconds: number; cooldown_remaining: number; evidence_stale: boolean;
};
export type DetectionEvent = {
  id: string; table_id: number; event_type: string; confidence: number; timestamp: string;
  source: string; state: string; reason: string;
};
export type Snapshot = {
  type: 'snapshot'; server_time: string; timezone: string; mode: string;
  simulation_enabled: boolean; auto_open_enabled: boolean; camera_ready: boolean;
  cue_detector_ready: boolean; decision_config: {
    policy: string; presence_seconds: number; confidence_enter: number; confidence_exit: number;
    max_observation_gap_seconds: number; absence_grace_seconds: number;
    cooldown_seconds: number; cue_confidence: number;
  };
  tables: Table[]; events: DetectionEvent[]; active_count: number;
  revenue_vnd: number; running_amount_vnd: number;
};
export type Observation = {
  event_id: string; table_id: number; present: boolean; confidence: number; ambiguous: boolean;
};
