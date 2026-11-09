"""A simulated MetaTrader 5 for development (MOHZ_CONNECTOR=fake).

Built on the engine's own test double (engine-src/tests/fake_mt5.py), plus:
- login rules: a password starting with "wrong" is refused like a bad login;
  a server name containing "Real" logs in to a real-money account;
- the gold symbol is named the way that broker names it (XAUUSDm, XAUUSD.m, XAUUSD);
- 5-minute bars and ticks that follow a random walk in real time, with the
  broker filling stops and targets as price moves.
"""
import datetime as dt
import importlib.util
import random
import time
from collections import namedtuple
from zoneinfo import ZoneInfo

from ..config import get_config

NY = ZoneInfo("America/New_York")
SERVER_SHIFT_HOURS = 7          # MT5 server clock = New York + 7 (the usual broker setup)
Account = namedtuple("Account", "login trade_mode balance equity leverage server currency company")
Tick = namedtuple("Tick", "bid ask time")


def _base_class():
    path = get_config().engine_src / "tests" / "fake_mt5.py"
    spec = importlib.util.spec_from_file_location("mohz_engine_fake_mt5", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FakeMT5


def gold_name(server):
    s = (server or "").lower()
    if "exness" in s:
        return "XAUUSDm"
    if "justmarkets" in s:
        return "XAUUSD.m"
    return "XAUUSD"


def _server_epoch(utc):
    ny = utc.replace(tzinfo=dt.timezone.utc).astimezone(NY).replace(tzinfo=None)
    server = ny + dt.timedelta(hours=SERVER_SHIFT_HOURS)
    return int((server - dt.datetime(1970, 1, 1)).total_seconds())


def _market_open(utc):
    ny = utc.replace(tzinfo=dt.timezone.utc).astimezone(NY)
    wd, h = ny.weekday(), ny.hour
    if wd == 5 or (wd == 6 and h < 18) or (wd == 4 and h >= 17):
        return False
    return h != 17


def FakeLiveMT5():   # noqa: N802  (a factory that looks like the module)
    Base = _base_class()

    class _Fake(Base):
        def __init__(self):
            super().__init__(trade_mode=0, balance=10000.0, symbol="XAUUSD")
            self.logged_in = None
            self._bars, self._last_bar_t, self._last_tick = [], None, time.time()
            self._rng = random.Random(7)

        # -- terminal
        def initialize(self, path=None, login=None, password=None, server=None, timeout=None, portable=False):
            if login is not None:
                if not password or str(password).startswith("wrong"):
                    self._err = (-6, "Terminal: Authorization failed")
                    return False
                self.logged_in = (int(login), server or "")
                self.trade_mode = 2 if "real" in (server or "").lower() else 0
                self.symbol = gold_name(server)
            self.initialized += 1
            self._err = (1, "Success")
            return True

        def shutdown(self):
            return True

        def last_error(self):
            return getattr(self, "_err", (1, "Success"))

        def account_info(self):
            if not self.logged_in:
                return None
            eq = self.balance + sum(self._profit(p) for p in self.positions)
            return Account(self.logged_in[0], self.trade_mode, round(self.balance, 2), round(eq, 2), 500,
                           self.logged_in[1], "USD", "Simulated broker")

        # -- prices
        def _now(self):
            return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

        def _build(self):
            now = self._now()
            step = dt.timedelta(minutes=5)
            end = now - dt.timedelta(seconds=now.timestamp() % 300)
            t = self._last_bar_t + step if self._last_bar_t else end - step * 17000
            price = self._bars[-1]["close"] if self._bars else 4000.0
            while t <= end:
                if _market_open(t):
                    o = price
                    moves = [self._rng.gauss(0, 0.9) for _ in range(5)]
                    path = [o]
                    for m in moves:
                        path.append(path[-1] + m)
                    price = round(path[-1], 2)
                    self._bars.append({"time": _server_epoch(t), "open": round(o, 2), "high": round(max(path) + 0.2, 2),
                                       "low": round(min(path) - 0.2, 2), "close": price, "tick_volume": 100})
                self._last_bar_t = t
                t += step
            self._bars = self._bars[-17000:]

        def copy_rates_from_pos(self, name, tf, start, count):
            self._build()
            return self._bars[-count:]

        def symbol_info_tick(self, name):
            self._build()
            now = time.time()
            if _market_open(self._now()) and now - self._last_tick > 1:
                base = self._bars[-1]["close"] if self._bars else 4000.0
                self.move(round(base + self._rng.gauss(0, 0.6), 2), spread=0.25)
                self._last_tick = now
            elif not self._bars:
                self.move(4000.0, spread=0.25)
            elif self.bid == 4005.0:      # first call while closed: last close
                self.move(self._bars[-1]["close"], spread=0.25)
            return Tick(self.bid, self.ask, _server_epoch(self._now()))

    return _Fake()
