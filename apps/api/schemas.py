from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SimulatedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    table_id: int = Field(ge=1, le=8)
    present: bool = True
    confidence: float = Field(default=.9, ge=0, le=1)
    ambiguous: bool = False
    cue_confidence: float | None = Field(default=None, ge=0, le=1)
    activity_state: Literal["PLAYING", "NOT_PLAYING", "UNKNOWN"] | None = None


class IngestionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    table_id: int = Field(ge=1, le=8)
    present: bool = True
    confidence: float = Field(default=.85, ge=0, le=1)
    ambiguous: bool = False
    cue_confidence: float | None = Field(default=None, ge=0, le=1)
    activity_state: Literal["PLAYING", "NOT_PLAYING", "UNKNOWN"] | None = None
    source: Literal["CAMERA", "VIDEO", "SIMULATED"] = "CAMERA"
    track_ids: list[int] = Field(default_factory=list)
    people_count: int = 1


class VideoActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)


class GenerateDemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: float = Field(default=35.0, ge=2.0, le=600.0)


class ExtractDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    interval: float = Field(default=2.0, ge=0.2, le=60.0)
