"""Settings from environment variables (and an optional .env file, which is gitignored).

Real environment variables win over .env. Nothing here is ever logged.
"""
import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        os.environ.setdefault(k, v)


def _bool(v, default=False):
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    database_url: str
    data_dir: Path
    broker_keys: dict          # key version -> 32-byte key
    cookie_secure: bool
    connector: str             # "mt5" (Windows + MetaTrader5) or "fake" (development)
    mt5_template_dir: str      # a portable MT5 install, copied once per broker account
    terminals_dir: Path
    probe_slots: int
    probe_timeout: float
    engine_src: Path
    trust_proxy: bool
    telegram_token: str
    telegram_username: str
    telegram_webhook_secret: str
    frontend_dist: Path
    session_days: int

    @property
    def accounts_dir(self):
        return self.data_dir / "accounts"


def _keys():
    """MOHZ_BROKER_KEY is the current key (version 1, or MOHZ_BROKER_KEY_VERSION).
    MOHZ_BROKER_KEY_OLD_<n> keeps older versions readable during a rotation."""
    import base64
    out = {}

    def dec(v, name):
        try:
            raw = base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))
        except ValueError:
            raise SystemExit("%s is not valid base64" % name)
        if len(raw) != 32:
            raise SystemExit("%s must be 32 bytes (base64). Make one with: python -m mohz.keygen" % name)
        return raw

    cur = os.environ.get("MOHZ_BROKER_KEY", "")
    if cur:
        out[int(os.environ.get("MOHZ_BROKER_KEY_VERSION", "1"))] = dec(cur, "MOHZ_BROKER_KEY")
    for k, v in os.environ.items():
        if k.startswith("MOHZ_BROKER_KEY_OLD_") and v:
            out[int(k.rsplit("_", 1)[1])] = dec(v, k)
    return out


def load_config():
    _load_dotenv(BACKEND_DIR / ".env")
    _load_dotenv(REPO_DIR / ".env")
    data_dir = Path(os.environ.get("MOHZ_DATA_DIR") or (REPO_DIR / "data")).resolve()
    return Config(
        database_url=os.environ.get("MOHZ_DATABASE_URL") or "sqlite:///%s" % (data_dir / "mohz.db").as_posix(),
        data_dir=data_dir,
        broker_keys=_keys(),
        cookie_secure=_bool(os.environ.get("MOHZ_COOKIE_SECURE"), True),
        connector=os.environ.get("MOHZ_CONNECTOR", "mt5"),
        mt5_template_dir=os.environ.get("MOHZ_MT5_TEMPLATE_DIR", ""),
        terminals_dir=Path(os.environ.get("MOHZ_TERMINALS_DIR") or (data_dir / "terminals")).resolve(),
        probe_slots=int(os.environ.get("MOHZ_PROBE_SLOTS", "2")),
        probe_timeout=float(os.environ.get("MOHZ_PROBE_TIMEOUT", "90")),
        engine_src=Path(os.environ.get("MOHZ_ENGINE_SRC") or (REPO_DIR / "engine-src")).resolve(),
        trust_proxy=_bool(os.environ.get("MOHZ_TRUST_PROXY"), False),
        telegram_token=os.environ.get("MOHZ_TELEGRAM_BOT_TOKEN", ""),
        telegram_username=os.environ.get("MOHZ_TELEGRAM_BOT_USERNAME", ""),
        telegram_webhook_secret=os.environ.get("MOHZ_TELEGRAM_WEBHOOK_SECRET", ""),
        frontend_dist=Path(os.environ.get("MOHZ_FRONTEND_DIST") or (REPO_DIR / "frontend" / "dist")).resolve(),
        session_days=int(os.environ.get("MOHZ_SESSION_DAYS", "14")),
    )


_config = None


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config():
    """Tests change the environment and call this."""
    global _config
    _config = None
