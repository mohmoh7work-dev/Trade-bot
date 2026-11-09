"""Broker accounts: add (with a real login test), edit, delete, detect the gold symbol,
start/stop the bot, per-account settings and the per-account log.

Every route loads the account through get_owned(), so a user can only ever see or act on
their own accounts. The broker password is write-only: it is encrypted on save and never
returned.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth import client_ip, current_user, enforce_limit, record_attempt
from ..config import get_config
from ..crypto import CryptoError, decrypt_password, encrypt_password
from ..db import get_db
from ..models import AccountEvent, AccountSnapshot, BotState, BrokerAccount
from ..settings_map import BotSettings, limits, load
from .common import accounts_for, get_owned, iso, serialize_account
from .me import check_own_password

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
LIVE_WORD = "LIVE"


def _clean(v, n):
    v = (v or "").strip()
    if not v or len(v) > n:
        raise ValueError("required, at most %d characters" % n)
    return v


class AccountIn(BaseModel):
    nickname: str = Field(max_length=60)
    platform: str = "MT5"
    broker: str = Field(max_length=80)
    server: str = Field(max_length=120)
    login: str = Field(max_length=20)
    password: str = Field(max_length=200)
    symbol: str = Field("XAUUSD", max_length=32)
    mode: str = "alerts"
    allow_live: bool = False
    confirm_password: str | None = Field(None, max_length=200)   # needed to turn on allow_live
    confirm_text: str | None = Field(None, max_length=10)

    @field_validator("nickname", "broker", "server", "symbol")
    @classmethod
    def _required(cls, v):
        return _clean(v, 120)

    @field_validator("login")
    @classmethod
    def _login(cls, v):
        v = (v or "").strip()
        if not v.isdigit() or len(v) > 20:
            raise ValueError("the MT5 login is the account number (digits only)")
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v not in ("auto", "alerts"):
            raise ValueError("mode must be auto or alerts")
        return v


class AccountPatch(BaseModel):
    nickname: str | None = Field(None, max_length=60)
    broker: str | None = Field(None, max_length=80)
    server: str | None = Field(None, max_length=120)
    login: str | None = Field(None, max_length=20)
    password: str | None = Field(None, max_length=200)            # empty / missing = keep the saved one
    symbol: str | None = Field(None, max_length=32)
    mode: str | None = None
    allow_live: bool | None = None
    confirm_password: str | None = Field(None, max_length=200)
    confirm_text: str | None = Field(None, max_length=10)


class DetectIn(BaseModel):
    server: str = Field(max_length=120)
    login: str = Field(max_length=20)
    password: str | None = Field(None, max_length=200)
    symbol: str = Field("XAUUSD", max_length=32)
    account_id: int | None = None          # editing: use the saved password if none was typed


def _platform(p):
    if (p or "MT5").upper() != "MT5":
        raise HTTPException(422, "Only MT5 accounts are supported.")
    return "MT5"


def _err(status, msg, code=None):
    return JSONResponse({"detail": msg, "code": code}, status_code=status)


async def _probe(request, db, user, server, login, password, symbol):
    ip = client_ip(request)
    enforce_limit(db, "probe", ip)
    record_attempt(db, "probe", ip, user.email, ok=True)
    cfg = get_config()
    return await request.app.state.probes.run({"server": server, "login": login, "password": password,
                                               "symbol": symbol}, cfg.probe_timeout)


def _broker_failed(res):
    if res.get("setup"):
        return _err(503, "The broker connection is not set up on this server: %s" % res.get("error"), "setup")
    code = res.get("code")
    msg = res.get("error") or "unknown error"
    return _err(400, "Login failed. The broker said: %s%s" % (msg, " (code %s)" % code if code is not None else ""),
                "login_failed")


def _check_live_confirm(db, request, user, body):
    if (body.confirm_text or "").strip().upper() != LIVE_WORD:
        raise HTTPException(422, "To allow real money, type %s to confirm." % LIVE_WORD)
    check_own_password(db, request, user, body.confirm_password or "")


def _taken(db, server, login, exclude_id=None):
    q = select(BrokerAccount).where(BrokerAccount.platform == "MT5",
                                    BrokerAccount.server_key == server.strip().lower(),
                                    BrokerAccount.login == login)
    other = db.scalar(q)
    if other is not None and other.id != exclude_id:
        return other
    return None


def _apply_probe(acct, res):
    a = res.get("account") or {}
    acct.account_type = a.get("type")
    acct.currency = a.get("currency")
    if res.get("mt5_offset_hours") is not None:
        acct.mt5_offset_hours = float(res["mt5_offset_hours"])
    if res.get("symbol"):
        acct.symbol = res["symbol"]


def _probe_summary(res):
    a = res.get("account") or {}
    return {"type": a.get("type"), "currency": a.get("currency"), "balance": a.get("balance"),
            "company": a.get("company"), "symbol": res.get("symbol"), "symbol_exact": res.get("symbol_exact"),
            "symbols": res.get("symbols") or []}


@router.get("")
def list_accounts(user=Depends(current_user), db=Depends(get_db)):
    return {"accounts": accounts_for(db, user), "limits": limits()}


@router.post("/detect")
async def detect(body: DetectIn, request: Request, user=Depends(current_user), db=Depends(get_db)):
    password = body.password or ""
    if not password and body.account_id is not None:
        acct = get_owned(db, user, body.account_id)
        try:
            password = decrypt_password(acct.password_enc, acct.user_id, acct.id)
        except CryptoError:
            raise HTTPException(422, "Type the account password to detect the symbol.")
    if not password:
        raise HTTPException(422, "Enter the server, login and password first.")
    res = await _probe(request, db, user, body.server.strip(), body.login.strip(), password, body.symbol.strip())
    del password
    if not res.get("ok"):
        return _broker_failed(res)
    if not res.get("symbol"):
        return _err(404, "No gold symbol found on this account.", "no_symbol")
    return _probe_summary(res)


@router.post("")
async def create(body: AccountIn, request: Request, user=Depends(current_user), db=Depends(get_db)):
    platform = _platform(body.platform)
    other = _taken(db, body.server, body.login)
    if other is not None:
        msg = "You already added this broker account." if other.user_id == user.id else \
            "This broker account is already connected to mohz bot."
        return _err(409, msg, "duplicate")
    if body.allow_live:
        _check_live_confirm(db, request, user, body)
    res = await _probe(request, db, user, body.server, body.login, body.password, body.symbol)
    if not res.get("ok"):
        return _broker_failed(res)
    if not res.get("symbol"):
        return _err(400, "Logged in, but this account has no gold symbol (looked for %s)." % body.symbol, "no_symbol")
    if (res.get("account") or {}).get("type") == "real" and not body.allow_live:
        return _err(400, "This is a real-money account. Turn on Allow real money to add it.", "real_account")
    acct = BrokerAccount(user_id=user.id, nickname=body.nickname, platform=platform, broker=body.broker,
                         server=body.server, server_key=body.server.strip().lower(), login=body.login,
                         symbol=body.symbol, mode=body.mode, allow_live=body.allow_live,
                         settings=BotSettings().dump())
    _apply_probe(acct, res)
    db.add(acct)
    try:
        db.flush()
        acct.password_enc = encrypt_password(body.password, user.id, acct.id)
        db.add(BotState(account_id=acct.id))
        db.add(AccountEvent(account_id=acct.id, kind="bot", level="info",
                            message="Account added: logged in to %s (%s account)." % (
                                body.login, (res.get("account") or {}).get("type") or "?")))
        db.commit()
    except IntegrityError:
        db.rollback()
        return _err(409, "This broker account is already connected to mohz bot.", "duplicate")
    except CryptoError as e:
        db.rollback()
        raise HTTPException(503, str(e))
    db.refresh(acct)
    return {"account": serialize_account(acct), "probe": _probe_summary(res)}


@router.patch("/{account_id}")
async def update(account_id: int, body: AccountPatch, request: Request, user=Depends(current_user),
                 db=Depends(get_db)):
    acct = get_owned(db, user, account_id)
    new = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump(exclude_unset=True).items()
           if k not in ("confirm_password", "confirm_text")}
    for k in ("nickname", "broker", "server", "symbol"):
        if k in new and not new[k]:
            raise HTTPException(422, "%s cannot be empty." % k.capitalize())
    if "login" in new and not (new["login"] or "").isdigit():
        raise HTTPException(422, "The MT5 login is the account number (digits only).")
    if "mode" in new and new["mode"] not in ("auto", "alerts"):
        raise HTTPException(422, "mode must be auto or alerts")
    password = new.pop("password", None) or None
    login_changed = any(k in new and new[k] != getattr(acct, k) for k in ("server", "login", "symbol")) or password
    live_on = new.get("allow_live") is True and not acct.allow_live
    live_change = "allow_live" in new and new["allow_live"] != acct.allow_live
    running = acct.state is not None and acct.state.desired == "running"
    if running and (login_changed or live_change):
        return _err(409, "Stop the bot before changing the server, login, password, symbol or real-money setting.",
                    "running")
    if live_on:
        _check_live_confirm(db, request, user, body)
    server, login = new.get("server", acct.server), new.get("login", acct.login)
    if login_changed and _taken(db, server, login, exclude_id=acct.id):
        return _err(409, "This broker account is already connected to mohz bot.", "duplicate")
    res = None
    if login_changed:
        try:
            pw = password or decrypt_password(acct.password_enc, acct.user_id, acct.id)
        except CryptoError:
            raise HTTPException(422, "Type the account password again.")
        res = await _probe(request, db, user, server, login, pw, new.get("symbol", acct.symbol))
        del pw
        if not res.get("ok"):
            return _broker_failed(res)
        if not res.get("symbol"):
            return _err(400, "Logged in, but this account has no gold symbol.", "no_symbol")
    allow_live = new.get("allow_live", acct.allow_live)
    acct_type = (res.get("account") or {}).get("type") if res else acct.account_type
    if acct_type == "real" and not allow_live:
        return _err(400, "This is a real-money account. Turn on Allow real money to keep it.", "real_account")
    for k, v in new.items():
        setattr(acct, k, v)
    acct.server_key = acct.server.strip().lower()
    if res:
        _apply_probe(acct, res)
    if password:
        acct.password_enc = encrypt_password(password, user.id, acct.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _err(409, "This broker account is already connected to mohz bot.", "duplicate")
    db.refresh(acct)
    return {"account": serialize_account(acct), "probe": _probe_summary(res) if res else None}


@router.delete("/{account_id}")
def remove(account_id: int, user=Depends(current_user), db=Depends(get_db)):
    """Deletes the account and its saved password. A running bot is stopped by the supervisor
    (closing trades if the account's settings say so)."""
    acct = get_owned(db, user, account_id)
    db.delete(acct)
    db.commit()
    return {"ok": True}


@router.post("/{account_id}/start")
def start(account_id: int, user=Depends(current_user), db=Depends(get_db)):
    acct = get_owned(db, user, account_id)
    if acct.account_type == "real" and not acct.allow_live:
        return _err(400, "This is a real-money account. Turn on Allow real money first.", "real_account")
    if not acct.password_enc:
        return _err(400, "Edit the account and type its password first.", "no_password")
    st = acct.state or BotState(account_id=acct.id)
    if st.desired != "running":
        st.desired, st.retries, st.next_retry_at, st.reason = "running", 0, None, None
        if st.status in ("stopped", "error"):
            st.status = "starting"
        snap = db.get(AccountSnapshot, acct.id)      # a fresh run: new numbers, new drawdown peak
        if snap is not None:
            db.delete(snap)
        db.add(st)
        db.add(AccountEvent(account_id=acct.id, kind="bot", level="info", message="Start requested."))
        db.commit()
    db.refresh(acct)
    return {"account": serialize_account(acct)}


@router.post("/{account_id}/stop")
def stop(account_id: int, user=Depends(current_user), db=Depends(get_db)):
    acct = get_owned(db, user, account_id)
    st = acct.state
    if st is not None and st.desired != "stopped":
        st.desired = "stopped"
        if st.pid is None and st.status in ("error", "starting"):
            st.status, st.reason = "stopped", None
        close = load(acct.settings).close_on_stop
        db.add(AccountEvent(account_id=acct.id, kind="bot", level="info",
                            message="Stop requested (%s)." % ("closing open trades" if close else "leaving open trades")))
        db.commit()
    db.refresh(acct)
    return {"account": serialize_account(acct)}


@router.get("/{account_id}/settings")
def get_settings(account_id: int, user=Depends(current_user), db=Depends(get_db)):
    acct = get_owned(db, user, account_id)
    return {"settings": load(acct.settings).dump(), "limits": limits()}


@router.put("/{account_id}/settings")
def put_settings(account_id: int, body: BotSettings, user=Depends(current_user), db=Depends(get_db)):
    acct = get_owned(db, user, account_id)
    acct.settings = body.dump()
    acct.settings_version = (acct.settings_version or 0) + 1
    db.add(AccountEvent(account_id=acct.id, kind="bot", level="info", message="Settings saved."))
    db.commit()
    db.refresh(acct)
    return {"account": serialize_account(acct)}


@router.get("/{account_id}/events")
def events(account_id: int, before: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=200),
           kind: str | None = Query(None, max_length=20), user=Depends(current_user), db=Depends(get_db)):
    get_owned(db, user, account_id)
    q = select(AccountEvent).where(AccountEvent.account_id == account_id)
    if before:
        q = q.where(AccountEvent.id < before)
    if kind == "trades":
        q = q.where(AccountEvent.kind.in_(("trade", "order", "signal")))
    elif kind == "decisions":
        q = q.where(AccountEvent.kind == "decision")
    elif kind == "errors":
        q = q.where(AccountEvent.level.in_(("warning", "error", "critical")))
    rows = db.scalars(q.order_by(AccountEvent.id.desc()).limit(limit)).all()
    return {"events": [{"id": e.id, "at": iso(e.at), "kind": e.kind, "level": e.level, "message": e.message,
                        "data": e.data} for e in rows],
            "more": len(rows) == limit}
