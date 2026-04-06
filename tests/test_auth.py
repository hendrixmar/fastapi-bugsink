import pytest
from fastapi import HTTPException

from auth import AuthenticatedUser, _decode_token


def test_decode_token_rejects_invalid_token():
    """A malformed JWT must raise a 401."""
    with pytest.raises(HTTPException) as exc_info:
        _decode_token("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_empty_string():
    """An empty token must raise a 401."""
    with pytest.raises(HTTPException) as exc_info:
        _decode_token("")
    assert exc_info.value.status_code == 401


def test_authenticated_user_from_claims():
    """AuthenticatedUser correctly maps JWT claims."""
    claims = {
        "sub": "abc-123",
        "email": "admin@example.com",
        "preferred_username": "admin",
        "groups": ["admin", "users"],
    }
    user = AuthenticatedUser.from_claims(claims)
    assert user.sub == "abc-123"
    assert user.email == "admin@example.com"
    assert user.username == "admin"
    assert "admin" in user.groups


def test_authenticated_user_from_claims_missing_fields():
    """Missing optional claims default to empty values."""
    claims = {"sub": "abc-123"}
    user = AuthenticatedUser.from_claims(claims)
    assert user.sub == "abc-123"
    assert user.email == ""
    assert user.username == ""
    assert user.groups == []
