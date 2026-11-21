"""Validated runtime performance settings, independent of image libraries."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisionPerformanceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_fps: float = Field(default=30, ge=1, le=60)
    observation_fps: float = Field(default=5, ge=1, le=30)
    opencv_threads: int = Field(default=1, ge=1, le=16)
    decoder_threads: int = Field(default=2, ge=1, le=16)
    dml_device_id: int = Field(default=0, ge=0, le=8)
    cue_enabled: bool = False
    preview_width: int = Field(default=960, ge=320, le=3840)
    jpeg_quality: int = Field(default=75, ge=40, le=95)

    @model_validator(mode="after")
    def validate_rates(self) -> "VisionPerformanceConfig":
        if self.observation_fps > self.target_fps:
            raise ValueError("observation_fps must not exceed target_fps")
        return self
