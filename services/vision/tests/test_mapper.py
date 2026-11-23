"""Unit tests for Table Zone Mapper & Ambiguity Resolution (SB-12)."""
import pytest

from services.vision.calibration import CalibrationConfig, TableZone
from services.vision.contracts import Detection
from services.vision.decision import DecisionConfig, Memory, advance
from services.vision.detector import PersonDetection
from services.vision.mapper import TableZoneMapper


@pytest.fixture
def sample_calibration() -> CalibrationConfig:
    # 2 tables: Table 1 on left, Table 2 on right, overlapping in x = [0.45, 0.55]
    return CalibrationConfig(
        camera_id="cam-test",
        calibration_status="CALIBRATED",
        coordinate_system="normalized_xy_0_1",
        tables=[
            TableZone(
                table_id=1,
                enabled=True,
                play_polygon=[[0.1, 0.1], [0.35, 0.1], [0.35, 0.4], [0.1, 0.4]],
                standing_polygon=[[0.05, 0.05], [0.5, 0.05], [0.5, 0.45], [0.05, 0.45]],
            ),
            TableZone(
                table_id=2,
                enabled=True,
                play_polygon=[[0.6, 0.1], [0.85, 0.1], [0.85, 0.4], [0.6, 0.4]],
                standing_polygon=[[0.45, 0.05], [0.95, 0.05], [0.95, 0.45], [0.45, 0.45]],
            ),
        ],
    )


def test_map_person_unambiguous(sample_calibration: CalibrationConfig):
    mapper = TableZoneMapper(sample_calibration)

    # Person stands at x=0.2, y=0.3 (firmly at Table 1)
    det1 = PersonDetection(
        bbox=(0.15, 0.1, 0.25, 0.3),
        confidence=0.9,
        foot_anchor=(0.2, 0.3),
        track_id=1,
    )
    assign1 = mapper.map_person(det1)
    assert assign1.status == "ASSIGNED"
    assert assign1.matched_tables == [1]
    assert assign1.track_id == 1


def test_map_person_outside(sample_calibration: CalibrationConfig):
    mapper = TableZoneMapper(sample_calibration)

    # Person stands in hallway at x=0.5, y=0.8 (outside all tables)
    det_out = PersonDetection(
        bbox=(0.45, 0.6, 0.55, 0.8),
        confidence=0.85,
        foot_anchor=(0.5, 0.8),
        track_id=2,
    )
    assign_out = mapper.map_person(det_out)
    assert assign_out.status == "OUTSIDE"
    assert assign_out.matched_tables == []


def test_map_person_ambiguous_overlapping_boundary(sample_calibration: CalibrationConfig):
    mapper = TableZoneMapper(sample_calibration)

    # Person stands at x=0.48, y=0.25 (in the overlap zone between Table 1 and Table 2)
    det_ambig = PersonDetection(
        bbox=(0.43, 0.1, 0.53, 0.25),
        confidence=0.92,
        foot_anchor=(0.48, 0.25),
        track_id=3,
    )
    assign = mapper.map_person(det_ambig)
    assert assign.status == "AMBIGUOUS"
    assert set(assign.matched_tables) == {1, 2}

    # When mapping frame with only this ambiguous person:
    assignments, summaries = mapper.map_frame([det_ambig])
    assert summaries[1].present is True
    assert summaries[1].ambiguous is True
    assert summaries[2].present is True
    assert summaries[2].ambiguous is True


def test_unambiguous_player_dominates_at_table(sample_calibration: CalibrationConfig):
    mapper = TableZoneMapper(sample_calibration)

    # Table 1 has player 1 firmly at Table 1
    p1 = PersonDetection(bbox=(0.15, 0.1, 0.25, 0.3), confidence=0.88, foot_anchor=(0.2, 0.3), track_id=1)
    # Player 2 stands on the border between Table 1 and Table 2
    p2 = PersonDetection(bbox=(0.43, 0.1, 0.53, 0.25), confidence=0.85, foot_anchor=(0.48, 0.25), track_id=2)

    _, summaries = mapper.map_frame([p1, p2])

    # Table 1 has an unambiguous player -> ambiguous is False
    assert summaries[1].present is True
    assert summaries[1].ambiguous is False
    assert summaries[1].people_count == 1

    # Table 2 only has the ambiguous player on border -> ambiguous is True
    assert summaries[2].present is True
    assert summaries[2].ambiguous is True


def test_ambiguity_invariant_with_temporal_fsm(sample_calibration: CalibrationConfig):
    """Verify acceptance criterion: AMBIGUOUS observation never opens a table."""
    mapper = TableZoneMapper(sample_calibration)
    det_ambig = PersonDetection(
        bbox=(0.43, 0.1, 0.53, 0.25),
        confidence=0.95,
        foot_anchor=(0.48, 0.25),
    )
    _, summaries = mapper.map_frame([det_ambig])
    obs_t1 = summaries[1].to_observation()

    config = DecisionConfig(presence_seconds=4.0)
    memory = Memory()
    now = 1000.0

    # Even with high confidence and multiple frames, ambiguous never triggers candidate or open
    for i in range(10):
        decision = advance(memory, obs_t1, now + i, config)
        memory = decision.memory
        assert decision.should_open is False
        assert decision.reason == "AMBIGUOUS"
        assert memory.state == "EMPTY"


def test_disabled_table_emits_no_observations_and_does_not_cause_ambiguity():
    cfg = CalibrationConfig(
        camera_id="cam-test",
        calibration_status="CALIBRATED",
        coordinate_system="normalized_xy_0_1",
        tables=[
            TableZone(
                table_id=1,
                enabled=True,
                play_polygon=[[0.1, 0.1], [0.35, 0.1], [0.35, 0.4], [0.1, 0.4]],
                standing_polygon=[[0.05, 0.05], [0.5, 0.05], [0.5, 0.45], [0.05, 0.45]],
            ),
            TableZone(
                table_id=2,
                enabled=False,
                play_polygon=[[0.45, 0.1], [0.85, 0.1], [0.85, 0.4], [0.45, 0.4]],
                standing_polygon=[[0.4, 0.05], [0.95, 0.05], [0.95, 0.45], [0.4, 0.45]],
            ),
        ],
    )
    mapper = TableZoneMapper(cfg)

    # Person standing in the overlap region of T1 (enabled) and T2 (disabled) -> only T1 assigned
    det_overlap = PersonDetection(bbox=(0.42, 0.1, 0.48, 0.25), confidence=0.9, foot_anchor=(0.45, 0.25), track_id=1)
    # Person standing solely inside T2 (disabled) -> OUTSIDE
    det_t2_only = PersonDetection(bbox=(0.7, 0.1, 0.8, 0.25), confidence=0.9, foot_anchor=(0.75, 0.25), track_id=2)

    assign_overlap = mapper.map_person(det_overlap)
    assert assign_overlap.status == "ASSIGNED"
    assert assign_overlap.matched_tables == [1]

    assign_t2 = mapper.map_person(det_t2_only)
    assert assign_t2.status == "OUTSIDE"

    _, summaries = mapper.map_frame([det_overlap, det_t2_only])
    assert 1 in summaries
    assert 2 not in summaries
    assert summaries[1].ambiguous is False


def _kps(**entries: tuple[int, tuple[float, float, float]]) -> tuple[tuple[float, float, float], ...]:
    pts = [(0.0, 0.0, 0.0)] * 17
    for _, (idx, val) in entries.items():
        pts[idx] = val
    return tuple(pts)


def test_mapper_play_surface_affinity_resolves_overlapping_corridor(sample_calibration: CalibrationConfig):
    mapper = TableZoneMapper(sample_calibration)
    # Feet sit in overlap corridor (0.48, 0.35), but hands & torso clearly aim onto Table 1 (right edge x=0.35)
    kps = _kps(
        ls=(5, (0.41, 0.24, 0.9)),
        rs=(6, (0.42, 0.26, 0.9)),
        lw=(9, (0.34, 0.25, 0.9)),
        rw=(10, (0.39, 0.27, 0.9)),
        lh=(11, (0.47, 0.28, 0.9)),
        rh=(12, (0.48, 0.29, 0.9)),
    )
    det = PersonDetection(
        bbox=(0.33, 0.20, 0.50, 0.36),
        confidence=0.92,
        foot_anchor=(0.48, 0.35),
        track_id=21,
        keypoints=kps,
    )
    assign = mapper.map_person(det)
    assert assign.status == "ASSIGNED"
    assert assign.matched_tables == [1]

    _, summaries = mapper.map_frame([det])
    assert summaries[1].present is True and summaries[1].ambiguous is False
    assert summaries[2].present is False


def test_mapper_rescues_splayed_foot_and_perspective_foreground_occlusion():
    # Far Table 1 vs foreground Table 2 where player's lower legs are occluded down near Table 2
    cfg = CalibrationConfig(
        camera_id="cam-skew",
        calibration_status="CALIBRATED",
        coordinate_system="normalized_xy_0_1",
        tables=[
            TableZone(
                table_id=1,
                enabled=True,
                play_polygon=[[0.22, 0.18], [0.52, 0.18], [0.54, 0.30], [0.20, 0.30]],
                standing_polygon=[[0.18, 0.14], [0.56, 0.14], [0.58, 0.34], [0.16, 0.34]],
            ),
            TableZone(
                table_id=2,
                enabled=True,
                play_polygon=[[0.15, 0.45], [0.60, 0.45], [0.65, 0.72], [0.10, 0.72]],
                standing_polygon=[[0.08, 0.40], [0.68, 0.40], [0.72, 0.80], [0.05, 0.80]],
            ),
        ],
    )
    mapper = TableZoneMapper(cfg)

    # Splayed foot slightly outside Table 1 standing zone, leaning into head rail of Table 1
    kps_splayed = _kps(
        ls=(5, (0.18, 0.23, 0.9)),
        rs=(6, (0.19, 0.25, 0.9)),
        lw=(9, (0.22, 0.24, 0.9)),
        lh=(11, (0.13, 0.29, 0.9)),
        rh=(12, (0.14, 0.30, 0.9)),
    )
    det_splayed = PersonDetection(
        bbox=(0.11, 0.18, 0.23, 0.37),
        confidence=0.90,
        foot_anchor=(0.12, 0.37),
        track_id=22,
        keypoints=kps_splayed,
    )
    assign_splayed = mapper.map_person(det_splayed)
    assert assign_splayed.status == "ASSIGNED" and assign_splayed.matched_tables == [1]

    # Foreground occlusion: bottom bbox / foot clipped at Table 2's top standing border (y=0.41)
    # while shoulders & bridge hands lie directly on Table 1's bottom rail (y=0.29)
    kps_occluded = _kps(
        ls=(5, (0.37, 0.27, 0.9)),
        rs=(6, (0.41, 0.27, 0.9)),
        lw=(9, (0.39, 0.29, 0.9)),
        lh=(11, (0.38, 0.34, 0.9)),
        rh=(12, (0.41, 0.34, 0.9)),
    )
    det_occluded = PersonDetection(
        bbox=(0.34, 0.24, 0.44, 0.41),
        confidence=0.91,
        foot_anchor=(0.39, 0.41),
        track_id=23,
        keypoints=kps_occluded,
    )
    assign_occ = mapper.map_person(det_occluded)
    assert assign_occ.status == "ASSIGNED" and assign_occ.matched_tables == [1]
