"""FastAPI security dependencies."""

from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.security.auth import authentication_service
from backend.app.security.base import Principal, RolePermissionAuthorizer, TradingPermission

bearer_scheme = HTTPBearer(auto_error=False)
authorizer = RolePermissionAuthorizer()


async def current_principal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> Principal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return await authentication_service.principal_from_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_permission(permission: TradingPermission) -> Callable[[Principal], Principal]:
    async def dependency(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        try:
            authorizer.require(principal, permission)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return principal

    return dependency


__all__ = ["current_principal", "require_permission"]
