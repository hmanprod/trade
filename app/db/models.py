from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MTProtoSession(Base):
    __tablename__ = "mtproto_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(32))
    string_session: Mapped[str] = mapped_column(Text)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SourceGroup(Base):
    __tablename__ = "source_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RelayConfig(Base):
    __tablename__ = "relay_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    destination_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    destination_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    filter_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
