"""Tests for engine/auth.py — JWT auth and dev bypass."""
import os
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from engine.auth import DEV_USER_ID, get_current_user

_TEST_SECRET = "test-secret-key-long-enough-for-hs256"


def _make_token(secret: str = _TEST_SECRET, sub: str = "user-123", exp_offset: int = 3600) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset}
    return jwt.encode(payload, secret, algorithm="HS256")


# ── Dev bypass ────────────────────────────────────────────────────────────────

def test_dev_bypass_returns_dev_user():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        result = get_current_user(credentials=None)
    assert result == DEV_USER_ID


def test_dev_bypass_ignores_token_if_no_secret():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any.token.here")
    with patch("engine.auth._jwt_secret", return_value=None):
        result = get_current_user(credentials=creds)
    assert result == DEV_USER_ID


# ── Prod mode — missing token ─────────────────────────────────────────────────

def test_missing_token_raises_401():
    with patch("engine.auth._jwt_secret", return_value="supersecret"):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=None)
    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


# ── Prod mode — valid token ───────────────────────────────────────────────────

def test_valid_jwt_returns_sub():
    token = _make_token(sub="user-abc")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("engine.auth._jwt_secret", return_value=_TEST_SECRET):
        result = get_current_user(credentials=creds)
    assert result == "user-abc"


def test_valid_jwt_different_user():
    token = _make_token(sub="student-42")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("engine.auth._jwt_secret", return_value=_TEST_SECRET):
        result = get_current_user(credentials=creds)
    assert result == "student-42"


# ── Prod mode — invalid / malformed token ────────────────────────────────────

def test_wrong_secret_raises_401():
    token = _make_token(sub="user-xyz")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("engine.auth._jwt_secret", return_value="wrong-secret-key-long-enough-32b"):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=creds)
    assert exc_info.value.status_code == 401
    assert "Invalid" in exc_info.value.detail


def test_expired_token_raises_401():
    token = _make_token(sub="user-old", exp_offset=-10)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("engine.auth._jwt_secret", return_value=_TEST_SECRET):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=creds)
    assert exc_info.value.status_code == 401


def test_garbage_token_raises_401():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.jwt")
    with patch("engine.auth._jwt_secret", return_value="secret"):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=creds)
    assert exc_info.value.status_code == 401


# ── Missing sub claim ─────────────────────────────────────────────────────────

def test_token_without_sub_raises_401():
    payload = {"role": "anon", "exp": int(time.time()) + 3600}  # no sub
    token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("engine.auth._jwt_secret", return_value=_TEST_SECRET):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=creds)
    assert exc_info.value.status_code == 401
