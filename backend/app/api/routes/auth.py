"""Authentication and authorization API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from backend.app.security.auth import authentication_service
from backend.app.security.dependencies import bearer_scheme, current_principal
from backend.app.security.base import Principal

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    username: str
    roles: list[str]
    permissions: list[str]


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    try:
        pair = await authentication_service.login(payload.username, payload.password)
        return TokenResponse(**pair.__dict__)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    try:
        pair = await authentication_service.refresh(payload.refresh_token)
        return TokenResponse(**pair.__dict__)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout")
async def logout(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    await authentication_service.logout(credentials.credentials)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(principal: Annotated[Principal, Depends(current_principal)]) -> UserResponse:
    return UserResponse(
        username=principal.subject,
        roles=sorted(principal.roles),
        permissions=sorted(permission.value for permission in principal.permissions),
    )


__all__ = ["router"]
