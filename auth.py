"""Authentik OIDC token validation for FastAPI.

Usage:
    from auth import get_current_user, AuthenticatedUser

    @app.get("/protected")
    async def protected(user: AuthenticatedUser = Depends(get_current_user)):
        return {"hello": user.username}
"""

import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
from authlib.jose import jwt, JoseError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

AUTHENTIK_URL = os.environ.get(
    "AUTHENTIK_ISSUER_URL",
    "https://auth.artesanosdigitalescom.com.mx/application/o/bugsink/",
)
AUTHENTIK_CLIENT_ID = os.environ.get("AUTHENTIK_CLIENT_ID", "")

_bearer = HTTPBearer(auto_error=False)
_jwks_cache: Optional[dict] = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    async with httpx.AsyncClient() as client:
        oidc = await client.get(f"{AUTHENTIK_URL}.well-known/openid-configuration")
        oidc.raise_for_status()
        jwks_uri = oidc.json()["jwks_uri"]

        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        claims = jwt.decode(token, _jwks_cache or {})
        claims.validate()
        return dict(claims)
    except (JoseError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


@dataclass
class AuthenticatedUser:
    sub: str
    email: str
    username: str
    groups: list[str] = field(default_factory=list)

    @classmethod
    def from_claims(cls, claims: dict) -> "AuthenticatedUser":
        return cls(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            username=claims.get("preferred_username", ""),
            groups=claims.get("groups", []),
        )


async def get_current_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthenticatedUser:
    """FastAPI dependency: extract and validate JWT, return user."""
    if cred is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    await _get_jwks()
    claims = _decode_token(cred.credentials)
    return AuthenticatedUser.from_claims(claims)
