import datetime as dt
import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..auth import (check_password_rules, client_ip, clear_cookies, current_session, current_user, end_all_sessions,
                    enforce_limit, hash_password, record_attempt, verify_password)
from ..config import get_config
from ..db import get_db, utcnow
from ..models import TelegramLink, User
from .common import iso

router = APIRouter(prefix="/api", tags=["me"])
log = logging.getLogger("mohz.api")


def me_doc(user):
    cfg = get_config()
    return {"id": user.id, "name": user.name, "email": user.email, "created_at": iso(user.created_at),
            "plan": {"code": user.plan.code, "name": user.plan.name} if user.plan else None,
            "telegram": {"available": bool(cfg.telegram_token and cfg.telegram_username),
                         "connected": bool(user.telegram_chat_id)}}


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class DeleteIn(BaseModel):
    password: str = Field(max_length=200)


def check_own_password(db, request, user, password):
    ip = client_ip(request)
    enforce_limit(db, "password", ip, user.email)
    ok = verify_password(user.password_hash, password)
    record_attempt(db, "password", ip, user.email, ok=ok)
    if not ok:
        raise HTTPException(403, "Your password is not correct.")


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": me_doc(user)}


@router.patch("/me")
def rename(body: NameIn, user=Depends(current_user), db=Depends(get_db)):
    user.name = body.name.strip()
    db.commit()
    return {"user": me_doc(user)}


@router.post("/me/password")
def change_password(body: PasswordIn, request: Request, sess=Depends(current_session), user=Depends(current_user),
                    db=Depends(get_db)):
    check_own_password(db, request, user, body.current_password)
    check_password_rules(body.new_password)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    end_all_sessions(db, user.id, keep=sess.id)       # log out every other device
    db.commit()
    return {"ok": True}


@router.delete("/me")
def delete_me(body: DeleteIn, request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    """Deletes the user, their broker accounts (and saved passwords) and payments.
    Running bots are stopped by the supervisor, closing trades per each account's settings."""
    check_own_password(db, request, user, body.password)
    db.delete(user)
    db.commit()
    clear_cookies(response)
    return {"ok": True}


# -- Telegram alerts: the user opens t.me/<bot>?start=<code>, the bot's webhook links the chat
@router.post("/me/telegram")
def telegram_link(user=Depends(current_user), db=Depends(get_db)):
    cfg = get_config()
    if not (cfg.telegram_token and cfg.telegram_username):
        raise HTTPException(503, "Telegram alerts are not set up on this server.")
    code = secrets.token_urlsafe(16)
    db.add(TelegramLink(code=code, user_id=user.id, expires_at=utcnow() + dt.timedelta(minutes=15)))
    db.commit()
    return {"url": "https://t.me/%s?start=%s" % (cfg.telegram_username, code)}


@router.delete("/me/telegram")
def telegram_unlink(user=Depends(current_user), db=Depends(get_db)):
    user.telegram_chat_id = None
    db.commit()
    return {"user": me_doc(user)}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, db=Depends(get_db)):
    cfg = get_config()
    sent = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not cfg.telegram_webhook_secret or not hmac.compare_digest(sent, cfg.telegram_webhook_secret):
        raise HTTPException(403, "forbidden")
    try:
        upd = await request.json()
    except ValueError:
        return {"ok": True}
    msg = (upd or {}).get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = (msg.get("chat") or {}).get("id")
    if not chat or not text.startswith("/start"):
        return {"ok": True}
    code = text.partition(" ")[2].strip()
    link = db.get(TelegramLink, code) if code else None
    reply = "Open mohz bot > Account and tap Connect Telegram to link this chat."
    if link and link.expires_at > utcnow():
        user = db.get(User, link.user_id)
        if user:
            user.telegram_chat_id = str(chat)
            reply = "Connected. mohz bot will send your alerts here."
        db.delete(link)
        db.commit()
    _send_telegram(chat, reply)
    return {"ok": True}


def _send_telegram(chat_id, text):
    import requests
    cfg = get_config()
    try:
        requests.post("https://api.telegram.org/bot%s/sendMessage" % cfg.telegram_token,
                      json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as e:
        log.warning("telegram reply failed: %s", type(e).__name__)
