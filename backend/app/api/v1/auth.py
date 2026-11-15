"""Register/login endpoints for individual student accounts."""
from __future__ import annotations

import re
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.auth import current_identity, hash_password, issue_token, verify_password, validate_auth_config
from backend.app.core.mysql import connect_mysql

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class Registration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    branch: str | None = Field(default=None, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=20, max_length=10000)


def _google_client_id() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


@router.get("/config")
def auth_config() -> dict:
    return {"google_client_id": _google_client_id() or None}


def verify_google_credential(credential: str, client_id: str) -> dict:
    """Verify a Google ID token signature, issuer, audience, expiry, and verified email."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token
    except ImportError as exc:
        raise HTTPException(503, "Google sign-in support is not installed. Install requirements.txt.") from exc
    try:
        claims = id_token.verify_oauth2_token(credential, Request(), audience=client_id)
    except Exception as exc:
        raise HTTPException(401, "Google sign-in could not verify this account. Please try again.") from exc
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "Google returned an invalid token issuer.")
    if claims.get("email_verified") is not True:
        raise HTTPException(403, "Verify your Google email address before continuing.")
    email = claims.get("email", "").strip().lower()
    subject = claims.get("sub", "")
    name = claims.get("name", "Google Student").strip()[:160]
    if not subject or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(401, "Google did not provide a valid verified email.")
    return {"email": email, "name": name or "Google Student"}


@router.post("/register", status_code=201)
def register(body: Registration) -> dict:
    validate_auth_config()
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO student_profiles (display_name, email, branch) VALUES (%s,%s,%s)",
                           (body.display_name, body.email.lower(), body.branch))
            profile_id = cursor.lastrowid
            cursor.execute("INSERT INTO user_accounts (email, password_hash, profile_id) VALUES (%s,%s,%s)",
                           (body.email.lower(), hash_password(body.password), profile_id))
            user_id = cursor.lastrowid
        connection.commit()
        return {"access_token": issue_token(user_id, profile_id), "token_type": "bearer",
                "profile": {"id": profile_id, "display_name": body.display_name, "email": body.email.lower(), "branch": body.branch}}
    except Exception as exc:
        connection.rollback()
        if getattr(exc, "args", [None])[0] == 1062:
            raise HTTPException(409, "An account with this email already exists.") from exc
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503, "Account could not be created. Check the database migration.") from exc
    finally:
        connection.close()


@router.post("/login")
def login(body: Login) -> dict:
    validate_auth_config()
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT u.id AS user_id, u.profile_id, u.password_hash,
                                     p.display_name, p.email, p.branch
                              FROM user_accounts u JOIN student_profiles p ON p.id=u.profile_id
                              WHERE u.email=%s AND u.active=TRUE""", (body.email.lower(),))
            account = cursor.fetchone()
        if not account or not verify_password(body.password, account["password_hash"]):
            raise HTTPException(401, "Email or password is incorrect.")
        return {"access_token": issue_token(account["user_id"], account["profile_id"]), "token_type": "bearer",
                "profile": {key: account[key] for key in ("profile_id", "display_name", "email", "branch")} | {"id": account["profile_id"]}}
    finally:
        connection.close()


@router.post("/google")
def google_login(body: GoogleCredential) -> dict:
    client_id = _google_client_id()
    if not client_id:
        raise HTTPException(503, "Google sign-in is not configured. Set GOOGLE_CLIENT_ID in .env.")
    validate_auth_config()
    google_user = verify_google_credential(body.credential, client_id)
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT u.id AS user_id, u.profile_id, p.display_name, p.email
                              FROM user_accounts u JOIN student_profiles p ON p.id=u.profile_id
                              WHERE u.email=%s AND u.active=TRUE""", (google_user["email"],))
            account = cursor.fetchone()
            if account:
                user_id, profile_id = account["user_id"], account["profile_id"]
                display_name, email = account["display_name"], account["email"]
            else:
                cursor.execute("INSERT INTO student_profiles (display_name, email) VALUES (%s,%s)",
                               (google_user["name"], google_user["email"]))
                profile_id = cursor.lastrowid
                # Google-only accounts have a random, undisclosed password and use Google to sign in.
                cursor.execute("INSERT INTO user_accounts (email, password_hash, profile_id) VALUES (%s,%s,%s)",
                               (google_user["email"], hash_password(secrets.token_urlsafe(48)), profile_id))
                user_id, display_name, email = cursor.lastrowid, google_user["name"], google_user["email"]
        connection.commit()
        return {"access_token": issue_token(user_id, profile_id), "token_type": "bearer",
                "profile": {"id": profile_id, "display_name": display_name, "email": email}}
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, HTTPException):
            raise
        if getattr(exc, "args", [None])[0] == 1062:
            raise HTTPException(409, "A SkillProof account already exists for this email. Try signing in again.") from exc
        raise HTTPException(503, "Google sign-in could not create or load the account. Check the database migration.") from exc
    finally:
        connection.close()


@router.get("/me")
def me(identity: dict = Depends(current_identity)) -> dict:
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT p.id, p.display_name, p.email, p.branch
                              FROM student_profiles p JOIN user_accounts u ON u.profile_id=p.id
                              WHERE u.id=%s AND u.active=TRUE""", (identity["sub"],))
            profile = cursor.fetchone()
        if not profile:
            raise HTTPException(401, "Account is no longer active.")
        return {"profile": profile}
    finally:
        connection.close()
