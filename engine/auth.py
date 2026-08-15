"""JWT-based auth via Supabase (Day 11).

When SUPABASE_JWT_SECRET is set, every request must carry a valid Bearer token
and the user_id is extracted from the JWT `sub` claim.

When the env var is absent (local dev without Supabase), auth is bypassed and
a fixed dev user_id ("dev-user") is returned — so all existing tests and local
runs continue to work without changes.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)

DEV_USER_ID = "dev-user"


def _jwt_secret() -> Optional[str]:
    return os.getenv("SUPABASE_JWT_SECRET")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """FastAPI dependency — returns the authenticated user_id.

    In dev mode (no SUPABASE_JWT_SECRET), returns DEV_USER_ID.
    In prod mode, validates the Bearer JWT and returns the `sub` claim.
    """
    secret = _jwt_secret()
    if not secret:
        # Dev bypass — no Supabase configured
        return DEV_USER_ID

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        import jwt as pyjwt
        payload = pyjwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError("JWT has no sub claim")
        return user_id
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
