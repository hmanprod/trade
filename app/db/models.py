from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    source_groups: Mapped[list["SourceGroup"]] = relationship(back_populates="session")


class SourceGroup(Base):
    __tablename__ = "source_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("mtproto_session.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["MTProtoSession"] = relationship(back_populates="source_groups")

    __table_args__ = (UniqueConstraint("group_id", "session_id", name="uq_group_session"),)


class RelayConfig(Base):
    __tablename__ = "relay_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    destination_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    destination_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    filter_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
