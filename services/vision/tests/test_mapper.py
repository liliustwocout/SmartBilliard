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
