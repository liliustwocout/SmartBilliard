from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (CheckConstraint("hourly_rate >= 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    hourly_rate: Mapped[int] = mapped_column(Integer)
    memory: Mapped[dict] = mapped_column(JSON, default=dict)


class PlaySession(Base):
    __tablename__ = "play_sessions"
    __table_args__ = (
        Index("one_active_session_per_table", "table_id", unique=True,
              sqlite_where=text("status = 'ACTIVE'")),
        CheckConstraint("status IN ('ACTIVE', 'PAID')"),
        CheckConstraint("hourly_rate_snapshot >= 0"),
        CheckConstraint("total_amount IS NULL OR total_amount >= 0"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    hourly_rate_snapshot: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(32))
    evidence_source: Mapped[str | None] = mapped_column(String(20), nullable=True)


class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float]
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
