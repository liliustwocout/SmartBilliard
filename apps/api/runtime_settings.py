"""Runtime overrides edited from the web UI, stored apart from decision.toml and .env."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.api.config import Settings
from services.vision.decision import DecisionConfig

logger = logging.getLogger("smartbilliard.settings")

OVERRIDE_KEYS = {"decision", "auto_open", "camera_source"}


class DecisionUpdate(BaseModel):
    """Partial DecisionConfig; bounds and cross-field rules are enforced by DecisionConfig itself."""
    model_config = ConfigDict(extra="forbid")
    policy: Literal["PERSON_ONLY", "PERSON_AND_CUE", "POSE_AND_CUE"] | None = None
    presence_seconds: float | None = None
    confidence_enter: float | None = None
    confidence_exit: float | None = None
    max_observation_gap_seconds: float | None = None
    absence_grace_seconds: float | None = None
    cooldown_seconds: float | None = None
    cue_confidence: float | None = None
    unbilled_alert_seconds: float | None = None
    playing_hold_grace_seconds: float | None = None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: DecisionUpdate | None = None
    auto_open: bool | None = None
    confirm_auto_open: bool = False
    camera_source: str | None = Field(default=None, min_length=1, max_length=500)


class RateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hourly_rate: int = Field(ge=0, le=10_000_000)


def merge_decision(current: DecisionConfig, partial: dict[str, Any]) -> DecisionConfig:
    """Raises pydantic.ValidationError when the merged thresholds are invalid."""
    return DecisionConfig.model_validate({**current.model_dump(), **partial})


def apply_overrides(base: Settings, overrides: dict[str, Any]) -> Settings:
    changes: dict[str, Any] = {}
    if overrides.get("decision"):
        changes["decision"] = merge_decision(base.decision, overrides["decision"])
    if isinstance(overrides.get("auto_open"), bool):
        changes["auto_open"] = overrides["auto_open"]
    if isinstance(overrides.get("camera_source"), str) and overrides["camera_source"].strip():
        changes["camera_source"] = overrides["camera_source"].strip()
    return replace(base, **changes)


def load_overrides(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("not an object")
        return {k: v for k, v in raw.items() if k in OVERRIDE_KEYS}
    except (OSError, ValueError) as err:
        logger.warning("Ignoring unreadable runtime settings %s: %s", path, err)
        return {}


def save_overrides(path: Path | None, overrides: dict[str, Any]) -> None:
    if path is None:
        return
    if not overrides:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(overrides, file, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
