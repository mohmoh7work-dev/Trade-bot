"""Database connection. SQLite in development, Postgres in production (MOHZ_DATABASE_URL).

The API, the supervisor and every worker open their own connection to the same database.
"""
import datetime as dt

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_config


class Base(DeclarativeBase):
    pass


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


_engine = None
_Session = None


def make_db_engine(url):
    kw = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")      # several processes read and write
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
    return eng


def init_db(url=None):
    global _engine, _Session
    cfg = get_config()
    url = url or cfg.database_url
    if url.startswith("sqlite:///"):
        from pathlib import Path
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    _engine = make_db_engine(url)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(_engine)
    models.seed(_Session)
    return _engine


def session():
    if _Session is None:
        init_db()
    return _Session()


def get_db():
    """FastAPI dependency."""
    s = session()
    try:
        yield s
    finally:
        s.close()
