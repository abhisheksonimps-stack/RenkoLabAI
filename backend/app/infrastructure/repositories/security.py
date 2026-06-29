"""SQL-backed user repository adapter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.models.security import UserModel
from backend.app.security.base import TradingPermission
from backend.app.security.users import User


class SqlUserRepository:
    """UserRepository implementation backed by SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, username: str) -> User | None:
        model = await self._session.get(UserModel, username)
        return self._to_domain(model) if model is not None else None

    async def save(self, user: User) -> None:
        model = await self._session.get(UserModel, user.username)
        if model is None:
            model = UserModel(username=user.username, password_hash=user.password_hash)
            self._session.add(model)
        model.password_hash = user.password_hash
        model.roles = ",".join(sorted(user.roles))
        model.permissions = ",".join(sorted(permission.value for permission in user.permissions))
        model.is_active = user.is_active
        await self._session.flush()

    async def list(self) -> list[User]:
        result = await self._session.execute(select(UserModel).order_by(UserModel.username))
        return [self._to_domain(model) for model in result.scalars().all()]

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            username=model.username,
            password_hash=model.password_hash,
            roles=frozenset(role for role in model.roles.split(",") if role),
            permissions=frozenset(TradingPermission(value) for value in model.permissions.split(",") if value),
            is_active=model.is_active,
            created_at=model.created_at,
        )


__all__ = ["SqlUserRepository"]
