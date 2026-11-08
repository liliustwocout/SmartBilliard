"""Contracts only in Phase 2; no camera or pretrained cue claims."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Detection:
    camera_id: str
    timestamp: float
    kind: Literal["person", "hand", "cue"]
    bbox: tuple[float, float, float, float]
    confidence: float
    track_id: int | None = None


class CueDetector(Protocol):
    validated: bool

    def detect(self, frame: object, *, camera_id: str, timestamp: float) -> list[Detection]: ...


class VideoSource(Protocol):
    def read(self) -> tuple[bool, object | None]: ...

    def close(self) -> None: ...
