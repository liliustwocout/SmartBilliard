"""Validated settings for local cloth/geometry ROI proposals (no trained model)."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AutoRoiConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_width: int = Field(default=960, ge=320, le=1920)
    hue_min: int = Field(default=35, ge=0, le=179)
    hue_max: int = Field(default=135, ge=0, le=179)
    saturation_min: int = Field(default=70, ge=0, le=255)
    value_min: int = Field(default=60, ge=0, le=255)
    morphology_size: int = Field(default=5, ge=1, le=15)
    long_edge_opening_fraction: float = Field(default=0.25, gt=0, lt=0.5)
    min_area_ratio: float = Field(default=0.006, gt=0, lt=1)
    max_area_ratio: float = Field(default=0.55, gt=0, lt=1)
    min_cloth_coverage: float = Field(default=0.65, gt=0, le=1)
    min_aspect_ratio: float = Field(default=1.3, ge=1)
    max_aspect_ratio: float = Field(default=8.0, gt=1)
    max_long_edge_angle_degrees: float = Field(default=45, ge=0, le=90)
    polygon_epsilon: float = Field(default=0.02, gt=0, le=0.05)
    standing_margin: float = Field(default=0.55, gt=0, le=1)
    match_iou: float = Field(default=0.2, gt=0, le=1)

    @model_validator(mode="after")
    def check_ranges(self) -> "AutoRoiConfig":
        if self.hue_min >= self.hue_max:
            raise ValueError("auto ROI hue_min must be less than hue_max")
        if self.min_area_ratio >= self.max_area_ratio:
            raise ValueError("auto ROI min_area_ratio must be less than max_area_ratio")
        if self.min_aspect_ratio >= self.max_aspect_ratio:
            raise ValueError("auto ROI min_aspect_ratio must be less than max_aspect_ratio")
        if self.morphology_size % 2 == 0:
            raise ValueError("auto ROI morphology_size must be odd")
        return self
