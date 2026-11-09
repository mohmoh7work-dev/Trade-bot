"""One broker account's bot: the unchanged engine, wired to this account.

Started by the supervisor:  python -m mohz.worker <account_id>
- stdin, first line: {"password": "..."} (never on the command line or in the environment)
- stdin, later: "stop" = stop the bot (closing its trades if the account's settings say so)
- stdin closed = the supervisor went away: stop analysing, leave trades alone, exit

It builds the engine the way `python -m engine serve --broker mt5` does (engine/__main__.py:
make_engine), with this account's login, symbol, mode and settings, and runs the engine's own
Runner. Every 5 s it writes a heartbeat, balance/equity/today's P/L/positions and the engine's
events to the dashboard database, applies settings edits, and enforces the auto-stops.
"""
import datetime as dt
import json
import os
import queue
import socket
import sys
import threading
import time
import traceback

from . import redact
from .config import get_config
from .db import init_db, session, utcnow
from .engine_bridge import ensure_engine_path
from .events import translate
from .locks import FileLock
from .models import AccountEvent, AccountSnapshot, BotState, BrokerAccount, User
from .settings_map import engine_patch, load

EXIT_STOPPED = 0        # stopped on request
EXIT_CRASH = 1          # retry with backoff
EXIT_CONFIG = 2         # needs the user (no retry)
EXIT_BROKER = 3         # broker trouble: retry with backoff
EXIT_LOGIN = 10         # the broker refused the login (no retry)
EXIT_LIMIT = 11         # daily loss / drawdown auto-stop (no retry)
EXIT_LOCKED = 12        # another worker has this account (retry)
EXIT_DETACHED = 13      # the supervisor went away
NO_RETRY = {EXIT_STOPPED, EXIT_CONFIG, EXIT_LOGIN, EXIT_LIMIT}

HEARTBEAT_SECONDS = 5
DISCONNECTED_RESTART_SECONDS = 300


class WorkerExit(Exception):
    def __init__(self, code, reason=None):
        super().__init__(reason or "")
        self.code, self.reason = code, reason


def _is_login_error(msg):
    m = (msg or "").lower()
    return "authoriz" in m or "-6" in m or "invalid account" in m or "password" in m


class SharedCalendar:
    """The engine's calendar, with one cached file for all workers (one download an hour)."""

    def __init__(self, path, ttl_minutes=60):
        ensure_engine_path()
        from engine.engine import Calendar
        self.path, self.ttl = str(path), ttl_minutes
        self._file = Calendar(path=self.path)
        self._live = Calendar(fetch=True, ttl_minutes=ttl_minutes)

    def events(self, now):
        try:
            fresh = os.path.exists(self.path) and time.time() - os.path.getmtime(self.path) < self.ttl * 60
        except OSError:
            fresh = False
        if not fresh:
            ev = self._live.events(now)
            if ev is not None:
                tmp = self.path + ".tmp"
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump({"events": ev}, f)
                    os.replace(tmp, self.path)
                except OSError:
                    pass
                return ev
        return self._file.events(now)


class PrefixChannel:
    """Puts the account nickname in front of every alert."""

    def __init__(self, inner, prefix):
        self.inner, self.prefix, self.name = inner, prefix, inner.name

    def send(self, title, body, data):
        return self.inner.send("[%s] %s" % (self.prefix, title), body, data)


class Worker:
    def __init__(self, account_id, password, mt5, data_dir=None):
        ensure_engine_path()
        self.account_id = int(account_id)
        self._password = password
        self.mt5 = mt5
        cfg = get_config()
        self.dir = (data_dir or cfg.accounts_dir) / str(self.account_id)
        self.events = queue.Queue()
        self.eng = self.runner = self.conn = None
        self.settings_version = None
        self.mode = None
        self.close_on_stop = True
        self.disconnected_since = None
        self.nickname = ""

    # -- database helpers
    def _account(self, s):
        return s.get(BrokerAccount, self.account_id)

    def set_state(self, **fields):
        with session() as s:
            st = s.get(BotState, self.account_id)
            if st is None:
                return False
            for k, v in fields.items():
                setattr(st, k, v)
            s.commit()
            return True

    def add_event(self, kind, level, message, data=None):
        self.events.put((utcnow(), kind, level, message, data))

    def _flush_events(self, s):
        n = 0
        while n < 500:
            try:
                at, kind, level, message, data = self.events.get_nowait()
            except queue.Empty:
                break
            s.add(AccountEvent(account_id=self.account_id, at=at, kind=kind, level=level, message=message[:2000],
                               data=json.loads(json.dumps(data, default=str)) if data else None))
            n += 1

    def on_engine_event(self, kind, payload):
        try:
            t = translate(kind, payload, self.eng.settings["mode"] if self.eng else "auto")
        except Exception:
            return
        if t:
            self.add_event(*t)

    # -- start
    def boot(self, start_runner=True):
        from engine.broker import BrokerError
        from engine.data import g
        from engine.engine import Engine
        from engine.mt5_broker import ACCOUNT_DEMO, ACCOUNT_REAL, MT5Broker, MT5Connection, MT5Source
        from engine.notify import Notifier, TelegramChannel
        from engine.runner import Runner
        from engine.settings import DEFAULTS, deep_merge, strategy_cfg, validate
        from engine.store import Store
        from .connectors import ConnectorError, terminal_path

        with session() as s:
            acct = self._account(s)
            if acct is None:
                raise WorkerExit(EXIT_CONFIG, "this broker account no longer exists")
            user = s.get(User, acct.user_id)
            login, server, nickname = acct.login, acct.server, acct.nickname
            allow_live = acct.allow_live
            self.settings_version, self.mode = acct.settings_version, acct.mode
            bot = load(acct.settings)
            self.close_on_stop = bot.close_on_stop
            patch = engine_patch(acct, bot)
            chat_id = user.telegram_chat_id if user else None
        self.nickname = nickname
        try:
            term = terminal_path(self.account_id)
        except ConnectorError as e:
            raise WorkerExit(EXIT_CONFIG, str(e))

        store = Store(str(self.dir / "engine.db"))
        doc, _ = validate(deep_merge(store.load_settings() or DEFAULTS, patch))
        env = {"MT5_LOGIN": login, "MT5_PASSWORD": self._password, "MT5_SERVER": server}
        if term:
            env["MT5_TERMINAL_PATH"] = term
        conn = MT5Connection(self.mt5, env, doc)
        try:
            info = conn.connect()
        except BrokerError as e:
            msg = str(e)
            if _is_login_error(msg):
                raise WorkerExit(EXIT_LOGIN, "The broker refused the login: %s" % msg.replace("MT5 initialize failed: ", ""))
            raise WorkerExit(EXIT_BROKER, msg)
        # The connection keeps the login (in memory only) to reconnect after a drop.
        self._password = None
        self.conn = conn
        if info is None or str(info.login) != str(login):
            raise WorkerExit(EXIT_BROKER, "MT5 is not logged in to account %s" % login)
        if info.trade_mode == ACCOUNT_REAL and not allow_live:
            raise WorkerExit(EXIT_CONFIG, "This is a real-money account. Turn on Allow real money in Edit to trade it.")
        if info.trade_mode not in (ACCOUNT_DEMO, ACCOUNT_REAL):
            raise WorkerExit(EXIT_CONFIG, "Contest accounts are not supported.")

        changes = []
        if conn.symbol_changed:
            changes.append(("symbol",) + conn.symbol_changed)
            self.add_event("bot", "warning", "This account calls gold %s (not %s): using %s."
                           % (conn.symbol_changed[1], conn.symbol_changed[0], conn.symbol_changed[1]))
            with session() as s:
                a = self._account(s)
                if a is not None:
                    a.symbol = conn.symbol_changed[1]
                    s.commit()
        sym = self.mt5.symbol_info(doc["symbol"])
        if sym is not None:                 # lot sizing uses the broker's own contract
            for key, val in (("contract_size", float(sym.trade_contract_size)), ("min_lot", float(sym.volume_min)),
                             ("lot_step", float(sym.volume_step)), ("digits", int(sym.digits))):
                if doc.get(key) != val:
                    changes.append((key, doc.get(key), val))
                    doc[key] = val

        eng = Engine(store, MT5Source(conn, strategy_cfg(doc)), settings=doc,
                     calendar=SharedCalendar(get_config().data_dir / "calendar.json"))
        store.save_settings(eng.settings, g.iso_utc(g.utc_now()), "mohz dashboard", changes or [("*", None, "start")])
        eng.broker = MT5Broker(conn, eng.settings, store, emit=eng.emit)

        real_place = eng.broker.place

        def guarded_place(order, now):       # Alerts only: never an order, whatever calls this
            if eng.settings["mode"] != "auto":
                raise BrokerError("alerts-only mode: orders are never sent")
            return real_place(order, now)
        eng.broker.place = guarded_place

        equity = eng.broker.account()["equity"]
        with session() as s:
            snap = s.get(AccountSnapshot, self.account_id)
            peak = snap.peak_equity if snap and snap.peak_equity else None
        eng.peak_equity = max(equity, peak or equity)
        self.eng = eng
        eng.bus.subscribe(self.on_engine_event)
        problem = eng.broker.mode_problem()
        if problem:
            raise WorkerExit(EXIT_CONFIG, problem)
        eng.reconcile(g.utc_now())

        self.runner = Runner(eng)
        cfg = get_config()
        if cfg.telegram_token and chat_id:
            notifier = Notifier(eng, [PrefixChannel(TelegramChannel(cfg.telegram_token, chat_id), nickname)],
                                clock=self.runner.now)
            eng.bus.subscribe(notifier.handle)
        if start_runner:
            self.runner.start()
        kind = "real-money" if info.trade_mode == ACCOUNT_REAL else "demo"
        self.add_event("bot", "info", "Bot started on %s (%s account), %s, %s mode. Balance %.2f." % (
            login, kind, eng.settings["symbol"], "auto-trade" if eng.settings["mode"] == "auto" else "alerts-only",
            float(info.balance)))
        return eng

    # -- every few seconds
    def tick(self):
        from engine.broker import BrokerError
        eng, runner = self.eng, self.runner
        with session() as s:
            acct = self._account(s)
            st = s.get(BotState, self.account_id)
            if acct is None or st is None:
                raise WorkerExit(EXIT_STOPPED, "gone")
            if acct.settings_version != self.settings_version or acct.mode != self.mode:
                self._reload(acct)
            status_doc, positions, err = None, [], None
            try:
                with runner.lock:
                    status_doc = runner.status()
                    positions = eng.broker.positions()
            except BrokerError as e:
                err = "broker disconnected: %s" % e
            except Exception as e:
                err = "could not read the account: %s" % e

            now = utcnow()
            reason = err or eng.disconnected or runner.last_error or None
            if reason:
                self.disconnected_since = self.disconnected_since or now
            else:
                self.disconnected_since = None
            st.heartbeat_at = now
            st.status = "error" if reason else "running"
            st.reason = reason
            if status_doc:
                snap = s.get(AccountSnapshot, self.account_id) or AccountSnapshot(account_id=self.account_id)
                snap.at = now
                snap.balance, snap.equity = status_doc["balance"], status_doc["equity"]
                snap.floating_pnl = status_doc["floating_pnl"]
                snap.today_pnl = round(status_doc["realized_today"] + status_doc["floating_pnl"], 2)
                snap.bid, snap.ask = status_doc["bid"], status_doc["ask"]
                snap.market_open = status_doc["market_open"]
                snap.peak_equity = round(eng.peak_equity, 2)
                snap.positions = [{"ticket": p["id"], "side": p["side"], "lots": p["lots"],
                                   "open_price": p["open_price"], "sl": p["sl"], "tp": p["tp"],
                                   "profit": p.get("profit"), "leg": p.get("leg")} for p in positions]
                s.add(snap)
            self._flush_events(s)
            s.commit()
        if status_doc:
            self._check_limits(status_doc)
        if self.disconnected_since and (utcnow() - self.disconnected_since).total_seconds() > DISCONNECTED_RESTART_SECONDS:
            raise WorkerExit(EXIT_BROKER, reason)
        if eng.halted and eng.halted.startswith(("broker error", "engine error")):
            raise WorkerExit(EXIT_BROKER, eng.halted)

    def _reload(self, acct):
        bot = load(acct.settings)
        live = bool(acct.allow_live and acct.account_type == "real")
        with self.runner.lock:
            try:
                changes, _ = self.eng.update_settings(engine_patch(acct, bot), actor="dashboard", allow_live=live)
            except (PermissionError, ValueError) as e:
                self.add_event("bot", "error", "Settings not applied: %s" % e)
                changes = None
        self.settings_version, self.mode = acct.settings_version, acct.mode
        self.close_on_stop = bot.close_on_stop
        if changes is not None:
            self.add_event("bot", "info", "Settings updated (%d change%s)." % (len(changes), "" if len(changes) == 1 else "s"))

    def _check_limits(self, st):
        eng = self.eng
        if eng.halted and eng.halted.startswith("drawdown"):
            raise WorkerExit(EXIT_LIMIT, "Auto-stopped: max %s. The bot closed its trades." % eng.halted)
        limit_pct = float(eng.settings["risk"]["daily_loss_pct"])
        today = st["realized_today"] + st["floating_pnl"]
        day_start = st["balance"] - st["realized_today"]
        if day_start > 0 and today <= -day_start * limit_pct / 100.0:
            from engine.data import g
            with self.runner.lock:
                eng.kill_switch(g.utc_now(), "daily loss limit")
            raise WorkerExit(EXIT_LIMIT, "Auto-stopped: daily loss limit reached (%.2f, %.1f%% of %.2f). "
                                         "The bot closed its trades." % (today, limit_pct, day_start))

    # -- stop
    def shutdown(self, close_trades):
        """Stop the engine; close its trades first if asked. Returns a problem or None."""
        problem = None
        if self.runner:
            self.runner.stop()
        if self.eng and close_trades:
            from engine.data import g
            try:
                with self.runner.lock:
                    if self.eng.broker.positions():
                        closed = self.eng.broker.close_all(g.utc_now(), "bot stopped")
                        self.add_event("trade", "info", "Stop: closed %d position(s)." % len(closed))
            except Exception as e:
                problem = "Could not close every trade (%s). Close them in MT5." % e
                self.add_event("error", "critical", problem)
        if self.conn is not None:
            try:
                with self.conn.lock:
                    self.mt5.shutdown()
            except Exception:
                pass
        return problem


def _stdin_watcher(stop, detach):
    for line in sys.stdin:
        if line.strip() == "stop":
            stop.set()
            return
    detach.set()


def _final_state(w, status, reason):
    try:
        with session() as s:
            w._flush_events(s)
            st = s.get(BotState, w.account_id)
            if st is not None:
                st.status, st.reason, st.pid = status, reason, None
                if status != "running":
                    st.heartbeat_at = None
            s.commit()
    except Exception:
        pass


def main(argv=None):
    redact.install()
    argv = argv if argv is not None else sys.argv[1:]
    account_id = int(argv[0])
    cfg = get_config()
    init_db()
    ensure_engine_path()
    lock = FileLock(cfg.accounts_dir / str(account_id) / "worker.lock")
    if not lock.acquire():
        return EXIT_LOCKED
    from .connectors import ConnectorError, load_mt5
    try:
        password = json.loads(sys.stdin.readline() or "{}").get("password") or ""
    except ValueError:
        password = ""
    try:
        mt5 = load_mt5()
    except ConnectorError as e:
        w = Worker(account_id, None, None)
        _final_state(w, "error", str(e))
        return EXIT_CONFIG
    w = Worker(account_id, password, mt5)
    del password
    w.set_state(status="starting", pid=os.getpid(), host=socket.gethostname(), reason=None, started_at=utcnow())
    stop, detach = threading.Event(), threading.Event()
    threading.Thread(target=_stdin_watcher, args=(stop, detach), daemon=True).start()
    try:
        w.boot()
        while not (stop.is_set() or detach.is_set()):
            w.tick()
            stop.wait(HEARTBEAT_SECONDS)
        if detach.is_set() and not stop.is_set():
            w.shutdown(close_trades=False)
            return EXIT_DETACHED
        problem = w.shutdown(close_trades=w.close_on_stop)
        w.add_event("bot", "info", "Bot stopped%s." % (" (open trades left as they are)" if not w.close_on_stop else ""))
        _final_state(w, "stopped", problem)
        return EXIT_STOPPED
    except WorkerExit as e:
        if e.reason == "gone":            # the account was deleted while running
            w.shutdown(close_trades=w.close_on_stop)
            return EXIT_STOPPED
        w.shutdown(close_trades=False)
        if e.reason:
            w.add_event("error" if e.code != EXIT_STOPPED else "bot", "error", e.reason)
        _final_state(w, "error", e.reason)
        return e.code
    except Exception as e:
        w.add_event("error", "error", "The bot crashed: %s" % e)
        w.add_event("log", "error", redact.redact(traceback.format_exc(limit=4)))
        w.shutdown(close_trades=False)
        _final_state(w, "error", "The bot crashed: %s" % e)
        return EXIT_CRASH
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
