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
