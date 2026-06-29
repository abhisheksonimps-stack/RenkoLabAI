"""Security primitives for production trading controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class TradingPermission(str, Enum):
    VIEW = "trading:view"
    SUBMIT_ORDER = "trading:submit_order"
    CANCEL_ORDER = "trading:cancel_order"
    MODIFY_ORDER = "trading:modify_order"
    MANAGE_RUNTIME = "trading:manage_runtime"
    KILL_SWITCH = "trading:kill_switch"


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[TradingPermission] = field(default_factory=frozenset)


class SecurityComponent:
    """Base security component."""

    @property
    def enabled(self) -> bool:
        return True


class RolePermissionAuthorizer(SecurityComponent):
    """Role-based trading permission authorizer."""

    def __init__(self, role_permissions: Mapping[str, Iterable[TradingPermission]] | None = None) -> None:
        self._role_permissions = {
            "viewer": frozenset({TradingPermission.VIEW}),
            "trader": frozenset({TradingPermission.VIEW, TradingPermission.SUBMIT_ORDER, TradingPermission.CANCEL_ORDER}),
            "admin": frozenset(TradingPermission),
        }
        if role_permissions is not None:
            self._role_permissions.update({role: frozenset(perms) for role, perms in role_permissions.items()})

    def allowed(self, principal: Principal, permission: TradingPermission) -> bool:
        if permission in principal.permissions:
            return True
        return any(permission in self._role_permissions.get(role, frozenset()) for role in principal.roles)

    def require(self, principal: Principal, permission: TradingPermission) -> None:
        if not self.allowed(principal, permission):
            raise PermissionError(f"{principal.subject} lacks {permission.value}")


class KillSwitch(SecurityComponent):
    """Process-local live-trading kill switch."""

    def __init__(self) -> None:
        self._engaged = False
        self._reason: str | None = None

    @property
    def engaged(self) -> bool:
        return self._engaged

    @property
    def reason(self) -> str | None:
        return self._reason

    def engage(self, reason: str) -> None:
        self._engaged = True
        self._reason = reason

    def release(self) -> None:
        self._engaged = False
        self._reason = None

    def ensure_trading_allowed(self) -> None:
        if self._engaged:
            raise RuntimeError(f"Trading disabled by kill switch: {self._reason}")


__all__ = [
    "KillSwitch",
    "Principal",
    "RolePermissionAuthorizer",
    "SecurityComponent",
    "TradingPermission",
]
