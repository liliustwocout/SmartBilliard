from dataclasses import replace

import pytest
from pydantic import ValidationError

from services.vision.decision import DecisionConfig, Memory, Observation, advance

CFG = DecisionConfig(presence_seconds=3, max_observation_gap_seconds=2, absence_grace_seconds=2)
PRESENT = Observation(True, .9)


def feed(*, config=CFG, auto_open=False, cue_detector_ready=False, observation=PRESENT):
    memory = Memory()
    for now in (0, 1, 2, 3):
        result = advance(memory, observation, now, config, auto_open=auto_open,
                         cue_detector_ready=cue_detector_ready)
        memory = result.memory
    return result


def test_person_baseline_requires_staff_by_default():
    result = feed()
    assert result.memory.state == "NEEDS_CONFIRMATION"
    assert not result.should_open


def test_controlled_simulation_can_open_after_real_duration():
    result = feed(auto_open=True)
    assert result.should_open and result.memory.state == "ACTIVE"


@pytest.mark.parametrize("observation", [Observation(False, 0), Observation(True, .99, True), Observation(True, .2)])
def test_empty_passers_ambiguous_and_low_confidence_do_not_open(observation):
    assert feed(auto_open=True, observation=observation).memory.state == "EMPTY"


def test_a_passer_does_not_reach_presence_duration():
    result = advance(Memory(), PRESENT, 0, CFG, auto_open=True)
    result = advance(result.memory, Observation(False, 0), 1, CFG, auto_open=True)
    result = advance(result.memory, Observation(False, 0), 4, CFG, auto_open=True)
    assert result.memory.state == "EMPTY"
    assert not result.should_open


def test_hysteresis_retains_mid_confidence_but_cannot_start_with_it():
    medium = Observation(True, .6)
    assert advance(Memory(), medium, 0, CFG).memory.state == "EMPTY"
    first = advance(Memory(), PRESENT, 0, CFG)
    assert advance(first.memory, medium, 1, CFG).memory.candidate_since == 0


def test_low_fps_and_occlusion_reset_candidate_after_gap():
    first = advance(Memory(), PRESENT, 0, CFG)
    next_result = advance(first.memory, PRESENT, 10, CFG, auto_open=True)
    assert next_result.memory.candidate_since == 10
    assert not next_result.should_open


def test_brief_occlusion_is_smoothed():
    result = advance(Memory(), PRESENT, 0, CFG)
    result = advance(result.memory, Observation(False, 0), 1, CFG)
    result = advance(result.memory, PRESENT, 2, CFG)
    result = advance(result.memory, PRESENT, 3, CFG)
    assert result.memory.state == "NEEDS_CONFIRMATION"


def test_active_session_never_closes_due_to_missing_person():
    result = advance(Memory(state="ACTIVE"), Observation(False, 0), 9999, CFG, active=True)
    assert result.memory.state == "ACTIVE" and not result.should_open


def test_cooldown_blocks_reopening():
    result = advance(Memory(state="CLOSED", cooldown_until=100), PRESENT, 99, CFG, auto_open=True)
    assert result.reason == "COOLDOWN" and not result.should_open


def test_old_observation_cannot_advance_state():
    first = advance(Memory(), PRESENT, 10, CFG)
    result = advance(first.memory, PRESENT, 5, CFG)
    assert result.memory == first.memory and result.reason == "OUT_OF_ORDER"


def test_cue_numbers_are_not_a_validated_detector():
    config = CFG.model_copy(update={"policy": "PERSON_AND_CUE"})
    result = feed(config=config, auto_open=True, observation=replace(PRESENT, cue_confidence=1))
    assert result.reason == "CUE_NOT_READY" and not result.should_open


def test_validated_cue_contract_can_be_integrated_later():
    config = CFG.model_copy(update={"policy": "PERSON_AND_CUE"})
    result = feed(config=config, auto_open=True, cue_detector_ready=True,
                  observation=replace(PRESENT, cue_confidence=.9))
    assert result.should_open


@pytest.mark.parametrize("values", [{"confidence_exit": .9}, {"presence_seconds": 0},
                                      {"cooldown_seconds": -1}, {"policy": "UNKNOWN"},
                                      {"unbilled_alert_seconds": 0}])
def test_invalid_thresholds_fail_early(values):
    with pytest.raises(ValidationError):
        DecisionConfig(**values)


def test_spectator_and_cleaning_not_playing_posture_never_confirms():
    config = DecisionConfig(presence_seconds=3, policy="POSE_AND_CUE")
    memory = Memory()
    spectator_obs = Observation(present=True, confidence=0.95, activity_state="NOT_PLAYING")
    for now in range(15):
        res = advance(memory, spectator_obs, float(now), config)
        memory = res.memory
        assert res.reason == "NOT_PLAYING_POSTURE"
        assert memory.state == "EMPTY"
        assert memory.playing_since is None
        assert not memory.unbilled_alert


def test_pose_and_cue_policy_requires_playing_and_fires_unbilled_5m_alert():
    config = DecisionConfig(
        policy="POSE_AND_CUE",
        presence_seconds=3,
        max_observation_gap_seconds=5,
        playing_hold_grace_seconds=25,
        unbilled_alert_seconds=300,
    )
    memory = Memory()
    playing = Observation(present=True, confidence=0.9, activity_state="PLAYING")
    standing_between_shots = Observation(present=True, confidence=0.9, activity_state="NOT_PLAYING")

    # Confirm initial playing after 3s
    for now in (0.0, 1.0, 2.0, 3.0):
        res = advance(memory, playing, now, config)
        memory = res.memory
    assert memory.state == "NEEDS_CONFIRMATION"
    assert memory.playing_since == 0.0
    assert not memory.unbilled_alert

    # Player stands upright for 8s between shots (< 25s grace) -> playing_since preserved
    for now in (5.0, 8.0, 11.0):
        res = advance(memory, standing_between_shots, now, config)
        memory = res.memory
        assert memory.playing_since == 0.0

    # Resume strokes past 300s (5 minutes) without POS opening table -> alert fires
    t = 15.0
    while t <= 300.0:
        res = advance(memory, playing, t, config)
        memory = res.memory
        t += 4.0
    res = advance(memory, playing, 301.0, config)
    assert res.reason == "UNBILLED_PLAY_OVER_5M"
    assert res.memory.unbilled_alert is True

    # Staff opens table on POS -> alert clears
    opened = advance(res.memory, playing, 302.0, config, active=True)
    assert opened.memory.state == "ACTIVE"
    assert opened.memory.unbilled_alert is False
    assert opened.memory.playing_since is None
