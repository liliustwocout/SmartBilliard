import os
from dataclasses import dataclass
from pathlib import Path
import tomllib
from zoneinfo import ZoneInfo

from services.vision.decision import DecisionConfig

ROOT = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, str(default)).lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/smartbilliard.db"
    table_count: int = 4
    hourly_rate: int = 60000
    auto_open: bool = False
    simulation_enabled: bool = True
    timezone: str = "Asia/Ho_Chi_Minh"
    decision: DecisionConfig = DecisionConfig()

    def __post_init__(self):
        if not 1 <= self.table_count <= 8:
            raise ValueError("TABLE_COUNT must be 1..8")
        if not 0 <= self.hourly_rate <= 10000000:
            raise ValueError("HOURLY_RATE_VND must be 0..10000000")
        if not self.database_url.startswith("sqlite:"):
            raise ValueError("Phase 2 supports SQLite only")
        ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls):
        path = Path(os.environ.get("DECISION_CONFIG", str(ROOT / "configs/decision.toml")))
        with path.open("rb") as file:
            decision = DecisionConfig.model_validate(tomllib.load(file))
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            table_count=int(os.environ.get("TABLE_COUNT", "4")),
            hourly_rate=int(os.environ.get("HOURLY_RATE_VND", "60000")),
            auto_open=env_bool("AUTO_OPEN_ENABLED", False),
            simulation_enabled=env_bool("SIMULATION_ENABLED", True),
            timezone=os.environ.get("DISPLAY_TIMEZONE", cls.timezone), decision=decision,
        )
