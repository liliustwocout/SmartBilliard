"""Pure temporal policy shared by the simulator and future camera adapter."""
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy: Literal["PERSON_ONLY", "PERSON_AND_CUE"] = "PERSON_ONLY"
    presence_seconds: float = Field(default=8, gt=0, le=600)
    confidence_enter: float = Field(default=.75, ge=0, le=1)
    confidence_exit: float = Field(default=.55, ge=0, le=1)
    max_observation_gap_seconds: float = Field(default=2.5, gt=0, le=60)
    absence_grace_seconds: float = Field(default=3, ge=0, le=60)
    cooldown_seconds: float = Field(default=15, ge=0, le=600)
    cue_confidence: float = Field(default=.8, ge=0, le=1)

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


@dataclass(frozen=True)
class Memory:
    state: str = "EMPTY"
    candidate_since: float | None = None
    last_seen: float | None = None
    last_positive: float | None = None
    cooldown_until: float = 0


@dataclass(frozen=True)
class Decision:
    memory: Memory
    should_open: bool = False
    reason: str = "WAITING"


def advance(memory: Memory, observation: Observation, now: float,
            config: DecisionConfig, *, active: bool = False,
            auto_open: bool = False, cue_detector_ready: bool = False) -> Decision:
    if active:
        return Decision(replace(memory, state="ACTIVE", last_seen=now), reason="SESSION_ACTIVE")
    if now < memory.cooldown_until:
        return Decision(replace(memory, state="CLOSED", last_seen=now), reason="COOLDOWN")
    if memory.last_seen is not None and now < memory.last_seen:
        return Decision(memory, reason="OUT_OF_ORDER")
    if (memory.last_seen is not None and now - memory.last_seen > config.max_observation_gap_seconds
            or memory.last_positive is not None
            and now - memory.last_positive > config.absence_grace_seconds):
        memory = Memory(cooldown_until=memory.cooldown_until)
    threshold = config.confidence_enter if memory.state in ("EMPTY", "CLOSED") else config.confidence_exit
    positive = observation.present and not observation.ambiguous and observation.confidence >= threshold
    if not positive:
        reason = "AMBIGUOUS" if observation.ambiguous else "NO_RELIABLE_PRESENCE"
        return Decision(replace(memory, last_seen=now), reason=reason)
    since = memory.candidate_since if memory.candidate_since is not None else now
    memory = replace(memory, state="CANDIDATE", candidate_since=since,
                     last_seen=now, last_positive=now)
    if now - since < config.presence_seconds:
        return Decision(memory, reason="PRESENCE_PENDING")
    cue_ok = (cue_detector_ready and observation.cue_confidence is not None
              and observation.cue_confidence >= config.cue_confidence)
    if config.policy == "PERSON_AND_CUE" and not cue_ok:
        return Decision(replace(memory, state="NEEDS_CONFIRMATION"), reason="CUE_NOT_READY")
    if not auto_open:
        return Decision(replace(memory, state="NEEDS_CONFIRMATION"), reason="STAFF_REQUIRED")
    return Decision(replace(memory, state="ACTIVE"), should_open=True, reason="CONTROLLED_DEMO")
