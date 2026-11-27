"""Xác thực cục bộ bằng Argon2, session cookie HttpOnly, chống CSRF và giới hạn đăng nhập sai."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, utc_now
from .models import User, UserSession

SESSION_COOKIE_NAME = "a5_sid"
_PASSWORD_HASHER = PasswordHasher()
# Hash giả cố định dùng để cân bằng thời gian kiểm tra khi username không tồn tại
_DUMMY_HASH = _PASSWORD_HASHER.hash("timing-protection-never-matches-anything-real")

# Bộ nhớ tạm giới hạn đăng nhập sai: tối đa 5 lần / 300 giây
_FAILED_ATTEMPTS: dict[tuple[str, str], list[float]] = defaultdict(list)
MAX_FAILED_ATTEMPTS = 5
LOCK_WINDOW_SECONDS = 300


def hash_password(password: str) -> str:
    if len(password or "") < 8:
        raise ValueError("Mật khẩu phải dài ít nhất 8 ký tự.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, plain_password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def dummy_verify(plain_password: str) -> None:
    try:
        _PASSWORD_HASHER.verify(_DUMMY_HASH, plain_password or "")
    except Exception:
        pass


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def check_rate_limit(client_ip: str, username: str) -> None:
    now = time.monotonic()
    key = (client_ip or "local", (username or "").lower())
    recent = [t for t in _FAILED_ATTEMPTS[key] if (now - t) < LOCK_WINDOW_SECONDS]
    _FAILED_ATTEMPTS[key] = recent
    if len(recent) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau ít phút.",
        )


def record_login_failure(client_ip: str, username: str) -> None:
    key = (client_ip or "local", (username or "").lower())
    _FAILED_ATTEMPTS[key].append(time.monotonic())


def clear_login_failures(client_ip: str, username: str) -> None:
    key = (client_ip or "local", (username or "").lower())
    _FAILED_ATTEMPTS.pop(key, None)


def reset_rate_limiter_for_tests() -> None:
    _FAILED_ATTEMPTS.clear()


def create_user_session(db: Session, user: User, ttl_hours: int = 12) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    now = utc_now()
    sess = UserSession(
        token_hash=hash_session_token(raw_token),
        user_id=user.id,
        csrf_token=csrf_token,
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(sess)
    db.flush()
    return raw_token, csrf_token


def get_active_session(
    db: Session,
    session_cookie: str | None,
) -> tuple[User, UserSession] | None:
    if not session_cookie:
        return None
    token_hash = hash_session_token(session_cookie)
    sess = db.execute(select(UserSession).where(UserSession.token_hash == token_hash)).scalar_one_or_none()
    if not sess or sess.revoked_at is not None:
        return None
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= utc_now():
        return None
    user = db.execute(select(User).where(User.id == sess.user_id)).scalar_one_or_none()
    if not user or not user.active:
        return None
    return user, sess


def require_authenticated(
    request: Request,
    db: Session = Depends(get_db),
    a5_sid: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> tuple[User, UserSession]:
    pair = get_active_session(db, a5_sid)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập hoặc phiên đã hết hạn.")
    user, sess = pair
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, sess.csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Thiếu hoặc sai mã CSRF token.")
    return user, sess


def require_admin(
    auth_pair: tuple[User, UserSession] = Depends(require_authenticated),
) -> tuple[User, UserSession]:
    user, sess = auth_pair
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yêu cầu quyền Quản trị (Admin).")
    return user, sess
