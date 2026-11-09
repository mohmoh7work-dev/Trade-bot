"""Log in to a broker account once, report what is there, and log out.

Used on save (to test the credentials) and by the Detect button (to find the gold symbol).
It runs in its own process because the MetaTrader5 package binds a process to one terminal.

    echo '{"server": "...", "login": "...", "password": "...", "symbol": "XAUUSD", "terminal": "..."}' \
        | python -m mohz.probe

Prints one line: MOHZ_PROBE {json}. The password is never printed or logged.
"""
import asyncio
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

PREFIX = "MOHZ_PROBE "
TRADE_MODES = {0: "demo", 1: "contest", 2: "real"}


def broker_error(mt5):
    try:
        code, msg = mt5.last_error()
    except Exception:
        return "the terminal gave no reason", None
    msg = str(msg or "").replace("Terminal:", "").strip() or "unknown error"
    return msg, code


def offset_hours(mt5, symbol):
    """MT5 server clock minus New York time, from a live tick; None when the market is closed."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not getattr(tick, "time", 0):
        return None
    now = dt.datetime.now(dt.timezone.utc)
    diff = (int(tick.time) - now.timestamp()) / 3600.0
    whole = round(diff * 2) / 2              # some servers are on half hours
    if abs(diff - whole) > 0.1 or not -12 <= whole <= 14:
        return None                          # an old tick: the market is closed
    ny = now.astimezone(ZoneInfo("America/New_York")).utcoffset().total_seconds() / 3600.0
    return whole - ny


def probe(req, mt5):
    from engine.mt5_broker import find_gold_symbol, gold_like
    kw = {"login": int(req["login"]), "password": req["password"], "server": req["server"], "timeout": 60000}
    if req.get("terminal"):
        kw["path"] = req["terminal"]
    try:
        if not mt5.initialize(**kw):
            msg, code = broker_error(mt5)
            return {"ok": False, "error": msg, "code": code}
        acct = mt5.account_info()
        if acct is None:
            msg, code = broker_error(mt5)
            return {"ok": False, "error": "logged in, but the account could not be read (%s)" % msg, "code": code}
        if int(acct.login) != int(req["login"]):
            return {"ok": False, "error": "the terminal is logged in to a different account (%s)" % acct.login}
        wanted = (req.get("symbol") or "XAUUSD").strip()
        names = gold_like(mt5)
        symbol = wanted if mt5.symbol_select(wanted, True) else find_gold_symbol(mt5, wanted)
        contract = None
        if symbol and mt5.symbol_select(symbol, True):
            info = mt5.symbol_info(symbol)
            if info is not None:
                contract = {"contract_size": float(info.trade_contract_size), "min_lot": float(info.volume_min),
                            "lot_step": float(info.volume_step), "digits": int(info.digits)}
        return {"ok": True,
                "account": {"login": str(acct.login), "server": getattr(acct, "server", req["server"]),
                            "type": TRADE_MODES.get(int(acct.trade_mode), "unknown"),
                            "balance": float(acct.balance), "equity": float(acct.equity),
                            "currency": getattr(acct, "currency", None), "leverage": getattr(acct, "leverage", None),
                            "company": getattr(acct, "company", None)},
                "symbols": names, "symbol": symbol, "symbol_exact": symbol == wanted, "contract": contract,
                "mt5_offset_hours": offset_hours(mt5, symbol) if symbol else None}
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def main():
    from . import redact
    redact.install()
    from .engine_bridge import ensure_engine_path
    from .connectors import ConnectorError, load_mt5
    ensure_engine_path()
    try:
        req = json.loads(sys.stdin.readline())
        out = probe(req, load_mt5())
    except ConnectorError as e:
        out = {"ok": False, "error": str(e), "setup": True}
    except (ValueError, KeyError) as e:
        out = {"ok": False, "error": "bad request: %s" % type(e).__name__}
    except Exception as e:   # never echo the request back
        out = {"ok": False, "error": "the login check failed: %s" % type(e).__name__}
    sys.stdout.write(PREFIX + json.dumps(out) + "\n")
    sys.stdout.flush()


# -- called by the API
class ProbePool:
    """A few spare terminals for login checks; one check per terminal at a time."""

    def __init__(self, slots):
        self.free = asyncio.Queue()
        for i in range(1, max(1, slots) + 1):
            self.free.put_nowait("_probe_%d" % i)

    async def run(self, req, timeout):
        from .connectors import ConnectorError, terminal_path
        slot = await asyncio.wait_for(self.free.get(), timeout=timeout)
        try:
            try:
                term = await asyncio.to_thread(terminal_path, slot)
            except ConnectorError as e:
                return {"ok": False, "error": str(e), "setup": True}
            return await run_subprocess(dict(req, terminal=term), timeout)
        finally:
            self.free.put_nowait(slot)


def child_env():
    """The worker and probe processes never get the encryption key."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOHZ_BROKER_KEY")}
    from .config import BACKEND_DIR
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return env


async def run_subprocess(req, timeout):
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "mohz.probe", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=child_env())
    try:
        out, _ = await asyncio.wait_for(proc.communicate((json.dumps(req) + "\n").encode()), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"ok": False, "error": "the broker did not answer in %d seconds" % timeout}
    for line in reversed(out.decode("utf-8", "replace").splitlines()):
        if line.startswith(PREFIX):
            return json.loads(line[len(PREFIX):])
    return {"ok": False, "error": "the login check stopped unexpectedly"}


if __name__ == "__main__":
    main()
