"""Shared helpers for the routes: ownership checks and what the browser gets for an account.

The serialized account never contains the broker password, its ciphertext, or anything
derived from it: only `password_set`.
"""
from fastapi import HTTPException
from sqlalchemy import func, select

from ..db import utcnow
from ..models import AccountEvent, BrokerAccount
from ..settings_map import load

STALE_HEARTBEAT = 60


def get_owned(db, user, account_id):
    """The account, if it belongs to this user. 404 otherwise (never reveals other users' ids)."""
    acct = db.get(BrokerAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Broker account not found.")
    return acct


def effective_state(st):
    """What the card should show, allowing for the supervisor not having caught up yet."""
    now = utcnow()
    if st is None:
        return {"status": "stopped", "desired": "stopped", "reason": None, "retry_at": None}
    status, reason = st.status, st.reason
    if st.desired == "running" and status == "stopped":
        status = "starting"
    if st.desired == "stopped" and status in ("running", "starting"):
        status = "stopping"
    if st.desired == "running" and status == "running" and st.heartbeat_at:
        silent = (now - st.heartbeat_at).total_seconds()
        if silent > STALE_HEARTBEAT:
            status, reason = "error", "No heartbeat from the bot for %d seconds." % silent
    retry_at = st.next_retry_at if (status == "error" and st.desired == "running" and st.next_retry_at) else None
    return {"status": status, "desired": st.desired, "reason": reason,
            "retry_at": iso(retry_at), "started_at": iso(st.started_at) if status == "running" else None,
            "heartbeat_at": iso(st.heartbeat_at)}


def iso(t):
    return t.isoformat() + "Z" if t else None


def serialize_account(acct, last_event_id=None):
    st = effective_state(acct.state)
    snap = acct.snapshot
    live = None
    # The snapshot is cleared on Start, so whatever is here belongs to the current run.
    if snap is not None and (st["desired"] == "running" or st["status"] == "stopping"):
        live = {"at": iso(snap.at), "balance": snap.balance, "equity": snap.equity, "today_pnl": snap.today_pnl,
                "floating_pnl": snap.floating_pnl, "bid": snap.bid, "ask": snap.ask,
                "market_open": snap.market_open, "positions": snap.positions or []}
    return {
        "id": acct.id, "nickname": acct.nickname, "platform": acct.platform, "broker": acct.broker,
        "server": acct.server, "login": acct.login, "symbol": acct.symbol, "mode": acct.mode,
        "allow_live": acct.allow_live, "account_type": acct.account_type, "currency": acct.currency,
        "password_set": bool(acct.password_enc), "settings": load(acct.settings).dump(),
        "bot": st, "live": live, "last_event_id": last_event_id,
        "created_at": iso(acct.created_at),
    }


def accounts_for(db, user):
    rows = db.scalars(select(BrokerAccount).where(BrokerAccount.user_id == user.id)
                      .order_by(BrokerAccount.created_at)).all()
    ids = [a.id for a in rows]
    last = {}
    if ids:
        last = dict(db.execute(select(AccountEvent.account_id, func.max(AccountEvent.id))
                               .where(AccountEvent.account_id.in_(ids)).group_by(AccountEvent.account_id)).all())
    return [serialize_account(a, last.get(a.id)) for a in rows]
