"""User passwords (argon2id), cookie sessions, CSRF and login rate limits.

- The session cookie `mohz_session` is httpOnly, Secure (unless MOHZ_COOKIE_SECURE=false
  in development) and SameSite=Lax. Only its SHA-256 is stored.
- `mohz_csrf` is readable by the page; every POST/PUT/PATCH/DELETE must echo it in the
  X-CSRF-Token header (double submit, checked against the session's own value).
- Login: at most 5 failures per email and 20 per IP address in 15 minutes.
"""
import datetime as dt
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select

from .config import get_config
from .db import get_db, utcnow
from .models import LoginAttempt, Session, User

COOKIE = "mohz_session"
CSRF_COOKIE = "mohz_csrf"
CSRF_HEADER = "x-csrf-token"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

_ph = PasswordHasher()
# Verified when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY = _ph.hash("not-a-real-password-just-for-timing")

LIMITS = {   # kind: (window minutes, max failures per email, max attempts per ip)
    "login": (15, 5, 20),
    "register": (60, None, 10),
    "probe": (10, None, 12),
    "password": (15, 5, 20),
}


def hash_password(pw):
    return _ph.hash(pw)


def verify_password(pw_hash, pw):
    try:
        return _ph.verify(pw_hash or _DUMMY, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_password_rules(pw):
    if len(pw) < 10:
        raise HTTPException(422, "Use at least 10 characters for your password.")
    if len(pw) > 200:
        raise HTTPException(422, "That password is too long.")


def client_ip(request: Request):
    if get_config().trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "?")[:64]


def _hash_token(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


# -- rate limits
def rate_limited(db, kind, ip, email=None):
    window, per_email, per_ip = LIMITS[kind]
    since = utcnow() - dt.timedelta(minutes=window)
    q = select(func.count()).select_from(LoginAttempt).where(LoginAttempt.kind == kind, LoginAttempt.at >= since)
    if per_email and email:
        n = db.scalar(q.where(LoginAttempt.email == email, LoginAttempt.ok.is_(False)))
        if n >= per_email:
            return True
    if per_ip:
        cond = LoginAttempt.ok.is_(False) if kind in ("login", "password") else True
        n = db.scalar(q.where(LoginAttempt.ip == ip, cond))
        if n >= per_ip:
            return True
    return False


def record_attempt(db, kind, ip, email="", ok=False):
    db.add(LoginAttempt(kind=kind, ip=ip, email=email or "", ok=ok))
    db.execute(delete(LoginAttempt).where(LoginAttempt.at < utcnow() - dt.timedelta(days=2)))
    db.commit()


def enforce_limit(db, kind, ip, email=None):
    if rate_limited(db, kind, ip, email):
        raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")


# -- sessions
def start_session(db, user, request: Request, response: Response):
    cfg = get_config()
    tok = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = utcnow()
    db.add(Session(id=_hash_token(tok), user_id=user.id, csrf=csrf, created_at=now, last_seen_at=now,
                   expires_at=now + dt.timedelta(days=cfg.session_days), ip=client_ip(request),
                   user_agent=(request.headers.get("user-agent") or "")[:255]))
    db.execute(delete(Session).where(Session.user_id == user.id, Session.expires_at < now))
    db.commit()
    max_age = cfg.session_days * 86400
    response.set_cookie(COOKIE, tok, max_age=max_age, httponly=True, secure=cfg.cookie_secure, samesite="lax",
                        path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=cfg.cookie_secure,
                        samesite="lax", path="/")
    return csrf


def end_session(db, request: Request, response: Response):
    tok = request.cookies.get(COOKIE)
    if tok:
        db.execute(delete(Session).where(Session.id == _hash_token(tok)))
        db.commit()
    clear_cookies(response)


def clear_cookies(response):
    cfg = get_config()
    response.delete_cookie(COOKIE, path="/", secure=cfg.cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=cfg.cookie_secure, samesite="lax")


def end_all_sessions(db, user_id, keep=None):
    q = delete(Session).where(Session.user_id == user_id)
    if keep:
        q = q.where(Session.id != keep)
    db.execute(q)


def session_from_request(db, request: Request):
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    sess = db.get(Session, _hash_token(tok))
    if sess is None or sess.expires_at < utcnow():
        return None
    return sess


def current_session(request: Request, db=Depends(get_db)):
    sess = session_from_request(db, request)
    if sess is None:
        raise HTTPException(401, "Please log in.")
    if request.method in UNSAFE:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf):
            raise HTTPException(403, "Security check failed. Reload the page and try again.")
    now = utcnow()
    if (now - sess.last_seen_at).total_seconds() > 300:
        sess.last_seen_at = now
        db.commit()
    return sess


def current_user(sess=Depends(current_session), db=Depends(get_db)):
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user
