"""The worker (the engine on one account) and the supervisor (one worker per account)."""
import datetime as dt
import time

import pytest

from mohz.db import utcnow

from conftest import BROKER_PASSWORD, account_body, csrf, new_user


def _make_account(client, **kw):
    new_user(client)
    h = csrf(client)
    a = client.post("/api/accounts", json=account_body(**kw), headers=h).json()["account"]
    return a, h


def _worker(aid, password=BROKER_PASSWORD):
    from mohz.connectors.fake import FakeLiveMT5
    from mohz.worker import Worker
    w = Worker(aid, password, FakeLiveMT5())
    w.boot(start_runner=False)
    return w


def _freeze(mt5, bid):
    mt5.move(bid, spread=0.25)
    mt5._last_tick = 1e18          # no more random ticks


def _order(eng, side="BUY", lots=0.02, sl=1.0, tp=9999.0):
    bid, ask = eng.broker.quote()
    return {"client_id": "sig-t%d" % int(time.time() * 1000), "signal_id": None, "side": side, "lots": lots,
            "entry": ask, "sl": sl, "tp1": tp - 1, "tp2": tp, "valid_until_utc": None}


def test_worker_reports_heartbeat_snapshot_and_events(client):
    a, _ = _make_account(client)
    w = _worker(a["id"])
    w.tick()
    from mohz.db import session
    from mohz.models import AccountSnapshot, BotState
    with session() as s:
        st, snap = s.get(BotState, a["id"]), s.get(AccountSnapshot, a["id"])
        assert st.heartbeat_at is not None and st.status == "running"
        assert snap.balance == 10000.0 and snap.positions == []
    ev = client.get("/api/accounts/%d/events" % a["id"]).json()["events"]
    assert any("Bot started" in e["message"] for e in ev)
    w.shutdown(close_trades=True)


def test_alerts_only_never_sends_orders(client):
    from engine.broker import BrokerError
    a, _ = _make_account(client, mode="alerts")
    w = _worker(a["id"])
    with pytest.raises(BrokerError):
        w.eng.broker.place(_order(w.eng), utcnow())
    assert w.mt5.positions == []
    w.shutdown(close_trades=True)


def test_stop_closes_trades_or_leaves_them(client):
    a, h = _make_account(client, mode="auto")
    w = _worker(a["id"])
    _freeze(w.mt5, 4000.0)
    w.eng.broker.place(_order(w.eng), utcnow())
    assert len(w.mt5.positions) == 2           # legs A and B
    assert w.shutdown(close_trades=True) is None
    assert w.mt5.positions == []

    w = _worker(a["id"])
    _freeze(w.mt5, 4000.0)
    w.eng.broker.place(_order(w.eng), utcnow())
    w.shutdown(close_trades=False)
    assert len(w.mt5.positions) == 2


def test_daily_loss_limit_auto_stops_and_closes(client):
    from mohz.worker import EXIT_LIMIT, WorkerExit
    a, h = _make_account(client, mode="auto")
    client.put("/api/accounts/%d/settings" % a["id"], json={"daily_loss_pct": 1.0}, headers=h)
    w = _worker(a["id"])
    _freeze(w.mt5, 4000.0)
    w.eng.broker.place(_order(w.eng, lots=0.05), utcnow())
    w.mt5.move(3970.0, spread=0.25)            # 0.05 lot x 100 oz x -30 = about -150 (1.5%)
    with pytest.raises(WorkerExit) as e:
        w.tick()
    assert e.value.code == EXIT_LIMIT and "daily loss" in e.value.reason
    assert w.mt5.positions == []


def test_settings_edit_reaches_running_engine(client):
    a, h = _make_account(client)
    w = _worker(a["id"])
    assert w.eng.settings["risk"]["max_open_trades"] == 1
    client.put("/api/accounts/%d/settings" % a["id"], json={"max_open_trades": 3, "max_spread": 0.4}, headers=h)
    client.patch("/api/accounts/%d" % a["id"], json={"mode": "auto"}, headers=h)
    w.tick()
    assert w.eng.settings["risk"]["max_open_trades"] == 3
    assert w.eng.settings["exits"]["max_spread"] == 0.4
    assert w.eng.settings["mode"] == "auto"
    w.shutdown(close_trades=True)


def test_bad_login_is_not_retried(client):
    from mohz.worker import EXIT_LOGIN, WorkerExit
    a, _ = _make_account(client)
    with pytest.raises(WorkerExit) as e:
        _worker(a["id"], password="wrong-one")
    assert e.value.code == EXIT_LOGIN and "Authorization failed" in e.value.reason


# -- supervisor, with fake processes
class FakeStdin:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, b):
        self.data += b

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProc:
    n = 0

    def __init__(self, args, **kw):
        FakeProc.n += 1
        self.pid = 1000 + FakeProc.n
        self.args, self.env = args, kw.get("env") or {}
        self.stdin = FakeStdin()
        self.code = None
        self.killed = False

    def poll(self):
        return self.code

    def kill(self):
        self.killed, self.code = True, -9

    def wait(self, timeout=None):
        return self.code


class Spawner:
    def __init__(self):
        self.procs = []

    def __call__(self, args, **kw):
        p = FakeProc(args, **kw)
        self.procs.append(p)
        return p


def _state(aid):
    from mohz.db import session
    from mohz.models import BotState
    with session() as s:
        return s.get(BotState, aid)


def test_supervisor_one_worker_backoff_and_no_retry_on_bad_login(client):
    from mohz.supervisor import STOP_TIMEOUT, Supervisor
    from mohz.worker import EXIT_LOGIN
    a, h = _make_account(client)
    sp = Spawner()
    sup = Supervisor(popen=sp)
    sup.step()
    assert sp.procs == []                                  # not started yet
    client.post("/api/accounts/%d/start" % a["id"], headers=h)
    now = utcnow()
    sup.step(now)
    sup.step(now)
    sup.step(now)
    mine = [p for p in sp.procs if p.args[-1] == str(a["id"])]
    assert len(mine) == 1                                  # never two workers for one account
    p = mine[0]
    assert BROKER_PASSWORD.encode() in p.stdin.data        # the password goes through stdin only...
    assert BROKER_PASSWORD not in " ".join(p.args)
    assert BROKER_PASSWORD not in " ".join(p.env.values())
    assert not any(k.startswith("MOHZ_BROKER_KEY") for k in p.env)   # ...and workers never get the key
    assert _state(a["id"]).status == "starting"

    p.code = 1                                             # crash
    sup.step(now)
    st = _state(a["id"])
    assert st.status == "error" and st.retries == 1
    assert 4 <= (st.next_retry_at - now).total_seconds() <= 6
    sup.step(now + dt.timedelta(seconds=2))
    assert len([p for p in sp.procs if p.args[-1] == str(a["id"])]) == 1     # waiting out the backoff
    sup.step(now + dt.timedelta(seconds=6))
    mine = [p for p in sp.procs if p.args[-1] == str(a["id"])]
    assert len(mine) == 2

    mine[-1].code = EXIT_LOGIN                             # bad login: no retry
    sup.step(now + dt.timedelta(seconds=7))
    st = _state(a["id"])
    assert st.status == "error" and st.desired == "stopped"
    sup.step(now + dt.timedelta(seconds=600))
    assert len([p for p in sp.procs if p.args[-1] == str(a["id"])]) == 2

    # stop: "stop" on stdin, killed if it hangs
    client.post("/api/accounts/%d/start" % a["id"], headers=h)
    t = now + dt.timedelta(seconds=700)
    sup.step(t)
    p = [p for p in sp.procs if p.args[-1] == str(a["id"])][-1]
    client.post("/api/accounts/%d/stop" % a["id"], headers=h)
    sup.step(t)
    assert p.stdin.data.endswith(b"stop\n") and _state(a["id"]).status == "stopping"
    sup.step(t + dt.timedelta(seconds=STOP_TIMEOUT + 1))
    assert p.killed
    sup.step(t + dt.timedelta(seconds=STOP_TIMEOUT + 2))
    assert _state(a["id"]).status == "stopped"


def test_supervisor_kills_silent_worker_and_restores_after_restart(client):
    from mohz.db import session
    from mohz.models import BotState
    from mohz.supervisor import HEARTBEAT_TIMEOUT, Supervisor
    a, h = _make_account(client)
    client.post("/api/accounts/%d/start" % a["id"], headers=h)
    sp = Spawner()
    sup = Supervisor(popen=sp)
    now = utcnow()
    sup.step(now)
    p = [p for p in sp.procs if p.args[-1] == str(a["id"])][-1]
    with session() as s:
        st = s.get(BotState, a["id"])
        st.status, st.heartbeat_at = "running", now
        s.commit()
    sup.step(now + dt.timedelta(seconds=HEARTBEAT_TIMEOUT + 5))
    assert p.killed
    sup.step(now + dt.timedelta(seconds=HEARTBEAT_TIMEOUT + 6))
    st = _state(a["id"])
    assert st.status == "error" and "stopped responding" in st.reason and st.desired == "running"

    # a new supervisor (server restart) brings running bots back
    sp2 = Spawner()
    sup2 = Supervisor(popen=sp2)
    sup2.restore()
    sup2.step(utcnow())
    assert [p.args[-1] for p in sp2.procs].count(str(a["id"])) == 1


def test_deleted_account_worker_is_stopped(client):
    from mohz.supervisor import Supervisor
    a, h = _make_account(client)
    client.post("/api/accounts/%d/start" % a["id"], headers=h)
    sp = Spawner()
    sup = Supervisor(popen=sp)
    sup.step()
    p = [p for p in sp.procs if p.args[-1] == str(a["id"])][-1]
    client.delete("/api/accounts/%d" % a["id"], headers=h)
    sup.step()
    assert p.stdin.data.endswith(b"stop\n")


def test_end_to_end_real_processes(client):
    """Supervisor + a real worker process on the simulated broker: start, run, stop."""
    from mohz.supervisor import Supervisor
    a, h = _make_account(client, mode="auto")
    client.post("/api/accounts/%d/start" % a["id"], headers=h)
    sup = Supervisor()
    deadline = time.time() + 90
    seen = None
    while time.time() < deadline:
        sup.step()
        acct = next(x for x in client.get("/api/accounts").json()["accounts"] if x["id"] == a["id"])
        seen = acct["bot"]["status"]
        if seen == "running" and acct["live"]:
            break
        time.sleep(0.5)
    assert seen == "running", acct["bot"]
    assert acct["live"]["balance"] == 10000.0
    client.post("/api/accounts/%d/stop" % a["id"], headers=h)
    deadline = time.time() + 60
    while time.time() < deadline:
        sup.step()
        if _state(a["id"]).status == "stopped" and a["id"] not in sup.procs:
            break
        time.sleep(0.5)
    assert _state(a["id"]).status == "stopped"
    ev = [e["message"] for e in client.get("/api/accounts/%d/events?limit=200" % a["id"]).json()["events"]]
    assert any(m.startswith("Bot started") for m in ev) and any(m.startswith("Bot stopped") for m in ev)
