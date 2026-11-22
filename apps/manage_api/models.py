from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata riêng của phòng quản lý; không dùng chung với apps.api.models.Base."""
