"""Tables.

users ─┬─ sessions
       ├─ payments ── plans
       └─ broker_accounts ─┬─ bot_state        (one row: wanted vs actual, heartbeat, retries)
                           ├─ account_snapshot (one row: balance, equity, today's P/L, positions)
                           └─ account_events   (every decision, signal, order, trade, error)
"""
import datetime as dt

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint, select)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    interval: Mapped[str] = mapped_column(String(10), default="month")     # month | year | once
    max_accounts: Mapped[int] = mapped_column(Integer, default=1)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    password_changed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    plan: Mapped[Plan | None] = relationship()
    accounts: Mapped[list["BrokerAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan",
                                                           passive_deletes=True)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)       # sha256 of the cookie value
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="login")       # login | register | probe
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Payment(Base):
    """Filled by a payment provider later (provider + provider_ref identify the charge there)."""
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "provider_ref"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending | paid | failed | refunded
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    plan: Mapped[Plan | None] = relationship()


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    # One broker login can be added once, by one user: two bots on one account would double-trade.
    __table_args__ = (UniqueConstraint("platform", "server_key", "login", name="uq_broker_login"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(60))
    platform: Mapped[str] = mapped_column(String(8), default="MT5")
    broker: Mapped[str] = mapped_column(String(80))
    server: Mapped[str] = mapped_column(String(120))
    server_key: Mapped[str] = mapped_column(String(120))     # server, trimmed + lower case
    login: Mapped[str] = mapped_column(String(20))
    password_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), default="XAUUSD")
    mode: Mapped[str] = mapped_column(String(8), default="alerts")       # auto | alerts
    allow_live: Mapped[bool] = mapped_column(Boolean, default=False)     # may trade a real-money account
    account_type: Mapped[str | None] = mapped_column(String(8), nullable=True)   # demo | real | contest
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    mt5_offset_hours: Mapped[float] = mapped_column(Float, default=7.0)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    settings_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")
    state: Mapped["BotState"] = relationship(cascade="all, delete-orphan", passive_deletes=True, uselist=False)
    snapshot: Mapped["AccountSnapshot"] = relationship(cascade="all, delete-orphan", passive_deletes=True,
                                                       uselist=False)


class BotState(Base):
    __tablename__ = "bot_state"
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id", ondelete="CASCADE"), primary_key=True)
    desired: Mapped[str] = mapped_column(String(8), default="stopped")    # running | stopped (what the user wants)
    status: Mapped[str] = mapped_column(String(10), default="stopped")    # stopped|starting|running|stopping|error
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    host: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshot"
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id", ondelete="CASCADE"), primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    today_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    floating_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_open: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    peak_equity: Mapped[float | None] = mapped_column(Float, nullable=True)   # for max drawdown across restarts
    positions: Mapped[list] = mapped_column(JSON, default=list)


class AccountEvent(Base):
    __tablename__ = "account_events"
    __table_args__ = (Index("ix_events_account_id_desc", "account_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(20))        # decision | signal | order | trade | error | bot | log
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TelegramLink(Base):
    __tablename__ = "telegram_links"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)


# Only the default plan is seeded. Add paid plans (and enforce max_accounts) when billing is wired up.
PLANS = [
    {"code": "free", "name": "Free", "price_cents": 0, "interval": "month", "max_accounts": 0},   # 0 = no limit
]


def seed(Session):
    with Session() as s:
        have = {p.code for p in s.scalars(select(Plan))}
        for p in PLANS:
            if p["code"] not in have:
                s.add(Plan(**p))
        s.commit()


def default_plan(s):
    return s.scalar(select(Plan).where(Plan.code == "free"))
