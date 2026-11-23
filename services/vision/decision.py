"""Pure temporal policy shared by the simulator and future camera adapter."""
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy: Literal["PERSON_ONLY", "PERSON_AND_CUE", "POSE_AND_CUE", "SMART_STANCE"] = "PERSON_ONLY"
    presence_seconds: float = Field(default=8, gt=0, le=600)
    confidence_enter: float = Field(default=.75, ge=0, le=1)
    confidence_exit: float = Field(default=.55, ge=0, le=1)
    max_observation_gap_seconds: float = Field(default=2.5, gt=0, le=60)
    absence_grace_seconds: float = Field(default=3, ge=0, le=60)
    cooldown_seconds: float = Field(default=15, ge=0, le=600)
    cue_confidence: float = Field(default=.8, ge=0, le=1)
    unbilled_alert_seconds: float = Field(default=300.0, gt=0, le=7200)
    playing_hold_grace_seconds: float = Field(default=25.0, ge=0, le=300)
    posture_pause_grace_seconds: float = Field(default=6.0, ge=0, le=60)

    @model_validator(mode="after")
    def thresholds(self):
        if self.confidence_exit > self.confidence_enter:
            raise ValueError("confidence_exit must be <= confidence_enter")
        return self


@dataclass(frozen=True)
class Observation:
    present: bool
    confidence: float
    ambiguous: bool = False
    cue_confidence: float | None = None
    activity_state: Literal["PLAYING", "NOT_PLAYING", "UNKNOWN"] | None = None
    felt_motion: bool = False
    sides_visited: int = 1
    activity_reason: str | None = None



@dataclass(frozen=True)
class Memory:
    state: str = "EMPTY"
    candidate_since: float | None = None
    last_seen: float | None = None
    last_positive: float | None = None
    cooldown_until: float = 0
    activity_state: str = "NOT_PLAYING"
    playing_since: float | None = None
    last_playing: float | None = None
    unbilled_alert: bool = False


@dataclass(frozen=True)
class Decision:
    memory: Memory
    should_open: bool = False
    reason: str = "WAITING"


def advance(memory: Memory, observation: Observation, now: float,
            config: DecisionConfig, *, active: bool = False,
            auto_open: bool = False, cue_detector_ready: bool = False) -> Decision:
    eff_activity = observation.activity_state or ("UNKNOWN" if observation.present else "NOT_PLAYING")

    if active:
        return Decision(
            replace(
                memory,
                state="ACTIVE",
                last_seen=now,
                activity_state=eff_activity,
                playing_since=None,
                last_playing=None,
                unbilled_alert=False,
            ),
            reason="SESSION_ACTIVE",
        )
    if now < memory.cooldown_until:
        return Decision(
            replace(memory, state="CLOSED", last_seen=now, activity_state=eff_activity, unbilled_alert=False),
            reason="COOLDOWN",
        )
    if memory.last_seen is not None and now < memory.last_seen:
        return Decision(memory, reason="OUT_OF_ORDER")

    gap_expired = (
        memory.last_seen is not None
        and (now - memory.last_seen) > config.max_observation_gap_seconds
    )
    play_still_held = (
        not gap_expired
        and memory.playing_since is not None
        and memory.last_playing is not None
        and (now - memory.last_playing) <= config.playing_hold_grace_seconds
    )
    absence_expired = (
        memory.last_positive is not None
        and (now - memory.last_positive) > config.absence_grace_seconds
    )
    candidate_posture_held = (
        not gap_expired
        and memory.state == "CANDIDATE"
        and memory.candidate_since is not None
        and memory.last_positive is not None
        and observation.present
        and not observation.ambiguous
        and observation.activity_reason != "CLEANING_MOTION"
        and (now - memory.last_positive) <= config.posture_pause_grace_seconds
    )
    if gap_expired or (absence_expired and not play_still_held and not candidate_posture_held):
        memory = Memory(cooldown_until=memory.cooldown_until)
        play_still_held = False
        candidate_posture_held = False

    threshold = config.confidence_enter if memory.state in ("EMPTY", "CLOSED") else config.confidence_exit
    base_positive = observation.present and not observation.ambiguous and observation.confidence >= threshold

    if observation.activity_state == "NOT_PLAYING" and not observation.felt_motion:
        positive = False
        reason = "NOT_PLAYING_POSTURE"
    elif config.policy == "POSE_AND_CUE" and observation.activity_state != "PLAYING" and not observation.felt_motion:
        positive = False
        reason = "AMBIGUOUS" if observation.ambiguous else "NO_RELIABLE_PRESENCE"
    elif config.policy == "SMART_STANCE":
        has_smart_play = (
            observation.activity_state == "PLAYING"
            or observation.felt_motion
            or observation.sides_visited >= 2
        )
        if not has_smart_play or (observation.activity_state == "NOT_PLAYING" and not observation.felt_motion):
            positive = False
            reason = "NOT_PLAYING_POSTURE" if observation.activity_state == "NOT_PLAYING" else "SPECTATOR_OR_IDLE"
        else:
            positive = base_positive
            reason = "AMBIGUOUS" if observation.ambiguous else "NO_RELIABLE_PRESENCE"
    else:
        positive = base_positive
        reason = "AMBIGUOUS" if observation.ambiguous else "NO_RELIABLE_PRESENCE"

    if not positive:
        if play_still_held and memory.playing_since is not None:
            alert = (now - memory.playing_since) >= config.unbilled_alert_seconds
            held_reason = "UNBILLED_PLAY_OVER_5M" if alert else reason
            return Decision(
                replace(
                    memory,
                    state="NEEDS_CONFIRMATION",
                    last_seen=now,
                    activity_state=eff_activity,
                    unbilled_alert=alert,
                ),
                reason=held_reason,
            )
        if candidate_posture_held:
            return Decision(
                replace(memory, last_seen=now, activity_state=eff_activity),
                reason=reason,
            )
        if observation.activity_state == "NOT_PLAYING" and not observation.felt_motion:
            return Decision(
                Memory(cooldown_until=memory.cooldown_until, last_seen=now, activity_state="NOT_PLAYING"),
                reason="NOT_PLAYING_POSTURE",
            )
        return Decision(replace(memory, last_seen=now, activity_state=eff_activity), reason=reason)

    since = memory.candidate_since if memory.candidate_since is not None else now
    updated = replace(
        memory,
        state="CANDIDATE",
        candidate_since=since,
        last_seen=now,
        last_positive=now,
        activity_state=eff_activity,
    )
    if now - since < config.presence_seconds:
        return Decision(updated, reason="PRESENCE_PENDING")

    cue_ok = (
        cue_detector_ready
        and observation.cue_confidence is not None
        and observation.cue_confidence >= config.cue_confidence
    )
    if config.policy == "PERSON_AND_CUE" and not cue_ok:
        return Decision(replace(updated, state="NEEDS_CONFIRMATION"), reason="CUE_NOT_READY")

    if not auto_open:
        playing_since = memory.playing_since if memory.playing_since is not None else since
        unbilled_alert = (now - playing_since) >= config.unbilled_alert_seconds
        confirm_reason = "UNBILLED_PLAY_OVER_5M" if unbilled_alert else "STAFF_REQUIRED"
        return Decision(
            replace(
                updated,
                state="NEEDS_CONFIRMATION",
                playing_since=playing_since,
                last_playing=now,
                unbilled_alert=unbilled_alert,
            ),
            reason=confirm_reason,
        )

    return Decision(
        replace(
            updated,
            state="ACTIVE",
            playing_since=None,
            last_playing=None,
            unbilled_alert=False,
        ),
        should_open=True,
        reason="CONTROLLED_DEMO",
    )
