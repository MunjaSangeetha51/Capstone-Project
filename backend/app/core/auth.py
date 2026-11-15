"""Small self-contained HS256 auth helpers; set a random APP_SECRET_KEY in production."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def _secret() -> bytes:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    secret = os.getenv("APP_SECRET_KEY", "")
    if len(secret) < 32:
        raise HTTPException(503, "Set APP_SECRET_KEY to a random value of at least 32 characters.")
    return secret.encode()


def validate_auth_config() -> None:
    _secret()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(derived).decode().rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt_text, digest_text = encoded.split("$")
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        expected = decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), decode(salt_text), int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(user_id: int, profile_id: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "profile_id": profile_id, "exp": int(time.time()) + 60 * 60 * 12}
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")
    body = f"{encode(header)}.{encode(payload)}"
    signature = base64.urlsafe_b64encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{body}.{signature}"


def current_identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Sign in to access this resource.", headers={"WWW-Authenticate": "Bearer"})
    try:
        header, payload, supplied = credentials.credentials.split(".")
        body = f"{header}.{payload}"
        expected = base64.urlsafe_b64encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        decode = lambda value: json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        claims = decode(payload)
        if claims.get("exp", 0) < time.time() or not isinstance(claims.get("profile_id"), int):
            raise ValueError
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Session expired or invalid. Sign in again.", headers={"WWW-Authenticate": "Bearer"})


def require_own_profile(profile_id: int, identity: dict = Depends(current_identity)) -> int:
    if identity["profile_id"] != profile_id:
        raise HTTPException(404, "Profile not found.")
    return profile_id
