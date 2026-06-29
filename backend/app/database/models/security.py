"""SQLAlchemy models for authentication and authorization."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.models.base import Base


class UserModel(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    roles: Mapped[str] = mapped_column(Text, nullable=False, default="viewer")
    permissions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class BrokerCredentialModel(Base):
    __tablename__ = "broker_credentials"

    exchange_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    api_key_ref: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    password_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


__all__ = ["BrokerCredentialModel", "UserModel"]
