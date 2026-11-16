"""Vision contracts and protocols for SmartBilliard (Phase 2 & Phase 3)."""
from dataclasses import dataclass
from typing import Literal, Protocol

SourceStatus = Literal["CONNECTED", "CONNECTING", "DISCONNECTED", "ERROR", "EOF", "CLOSED"]


@dataclass(frozen=True)
class Detection:
    camera_id: str
    timestamp: float
    kind: Literal["person", "hand", "cue"]
    bbox: tuple[float, float, float, float]
    confidence: float
    track_id: int | None = None
    foot_anchor: tuple[float, float] | None = None


class CueDetector(Protocol):
    validated: bool

    def detect(self, frame: object, *, camera_id: str, timestamp: float) -> list[Detection]: ...


class VideoSource(Protocol):
    camera_id: str

    @property
    def status(self) -> str: ...

    def read(self) -> tuple[bool, object | None]: ...

    def close(self) -> None: ...
