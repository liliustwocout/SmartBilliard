"""Cấu hình phòng quản lý. Hoàn toàn tách khỏi phòng demo: biến môi trường tiền tố MANAGE_,
cơ sở dữ liệu riêng, cổng riêng."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DEMO_DB_NAME = "smartbilliard.db"


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, str(default)).lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class ManageSettings:
    database_url: str = "sqlite:///./data/manage.db"
    timezone: str = "Asia/Ho_Chi_Minh"
    api_port: int = 8100
    web_port: int = 5174
    cookie_secure: bool = False
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    extra_origins: tuple[str, ...] = field(default_factory=tuple)
    payment_provider: str = "mock"

    def __post_init__(self):
        if not self.database_url.startswith("sqlite:"):
            raise ValueError("Phòng quản lý hiện chỉ hỗ trợ SQLite")
        if DEMO_DB_NAME in self.database_url:
            raise ValueError("MANAGE_DATABASE_URL không được trỏ tới cơ sở dữ liệu của phòng demo")
        if not (1 <= self.api_port <= 65535 and 1 <= self.web_port <= 65535):
            raise ValueError("Cổng không hợp lệ")
        if self.payment_provider != "mock":
            raise ValueError("MANAGE_PAYMENT_PROVIDER hiện chỉ hỗ trợ 'mock' (cọc giả lập, không thu tiền thật)")
        ZoneInfo(self.timezone)

    @property
    def allowed_origins(self) -> frozenset[str]:
        hosts = ("127.0.0.1", "localhost")
        base = {f"http://{h}:{p}" for h in hosts for p in (self.api_port, self.web_port)}
        return frozenset(base | set(self.extra_origins))

    @classmethod
    def from_env(cls) -> "ManageSettings":
        def csv(name: str) -> tuple[str, ...]:
            return tuple(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())

        return cls(
            database_url=os.environ.get("MANAGE_DATABASE_URL", cls.database_url),
            timezone=os.environ.get("MANAGE_TIMEZONE", cls.timezone),
            api_port=int(os.environ.get("MANAGE_API_PORT", cls.api_port)),
            web_port=int(os.environ.get("MANAGE_WEB_PORT", cls.web_port)),
            cookie_secure=env_bool("MANAGE_COOKIE_SECURE", False),
            allowed_hosts=csv("MANAGE_ALLOWED_HOSTS") or cls.allowed_hosts,
            extra_origins=csv("MANAGE_EXTRA_ORIGINS"),
            payment_provider=os.environ.get("MANAGE_PAYMENT_PROVIDER", cls.payment_provider),
        )
