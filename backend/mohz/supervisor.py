"""Keeps one worker process per broker account that should be running.

    python -m mohz.supervisor

The dashboard never starts processes itself: Start/Stop only set bot_state.desired in the
database, and this loop (once a second) makes reality match it:
- desired running, no worker  -> start one (after the backoff delay, if it failed before)
- desired stopped, a worker   -> send it "stop", kill it after STOP_TIMEOUT seconds
- worker silent for HEARTBEAT_TIMEOUT seconds -> kill it, show Error, retry with backoff
- worker exited -> record why; retry crashes and broker trouble, not bad logins or auto-stops
On start it restores every bot that was running. Only one supervisor can run (a lock file),
and one account can never have two workers (this map + a lock file per account).
"""
import datetime as dt
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from sqlalchemy import delete, select

from . import redact
from .config import get_config
from .crypto import CryptoError, decrypt_password
from .db import init_db, session, utcnow
from .locks import FileLock
from .models import AccountEvent, BotState, BrokerAccount
from .probe import child_env
from .worker import EXIT_CONFIG, EXIT_DETACHED, EXIT_LIMIT, EXIT_LOCKED, EXIT_LOGIN, EXIT_STOPPED, NO_RETRY

log = logging.getLogger("mohz.supervisor")

BACKOFF = [5, 15, 30, 60, 120, 300, 600]
STOP_TIMEOUT = 45            # closing trades can take a while
HEARTBEAT_TIMEOUT = 90
BOOT_TIMEOUT = 180           # a fresh terminal can be slow to log in the first time
HEALTHY_RESET = 600          # running this long without trouble: the retry count starts again
EVENT_DAYS = 90

EXIT_TEXT = {
    EXIT_CONFIG: "The bot could not start with this account's setup.",
    EXIT_LOGIN: "The broker refused the login.",
    EXIT_LIMIT: "Auto-stopped by a risk limit.",
    EXIT_LOCKED: "Another bot process still holds this account.",
}


@dataclass
class Proc:
    popen: subprocess.Popen
    started: dt.datetime
    stop_sent: dt.datetime | None = None
    log_file: object = None


def backoff(retries):
    return BACKOFF[min(max(retries, 1), len(BACKOFF)) - 1]


class Supervisor:
    def __init__(self, popen=subprocess.Popen):
        self.procs = {}
        self._popen = popen
        self._pruned = None

    # -- processes
    def spawn(self, s, st, now):
        acct = s.get(BrokerAccount, st.account_id)
        if acct is None:
            return
        try:
            password = decrypt_password(acct.password_enc, acct.user_id, acct.id)
        except CryptoError as e:
            st.desired, st.status = "stopped", "error"
            st.reason = "The saved broker password cannot be read (%s). Edit the account and type it again." % e
            return
        cfg = get_config()
        d = cfg.accounts_dir / str(acct.id)
        d.mkdir(parents=True, exist_ok=True)
        log_file = open(d / "worker.log", "ab")
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = self._popen([sys.executable, "-m", "mohz.worker", str(acct.id)], stdin=subprocess.PIPE,
                        stdout=log_file, stderr=log_file, env=child_env(), cwd=str(d), **kw)
        try:
            import json
            p.stdin.write((json.dumps({"password": password}) + "\n").encode())
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        del password
        self.procs[acct.id] = Proc(p, now, log_file=log_file)
        st.status, st.reason, st.pid, st.started_at, st.heartbeat_at = "starting", None, p.pid, now, None
        st.next_retry_at = None
        log.info("account %s: worker started (pid %s)", acct.id, p.pid)

    def send_stop(self, aid, proc, now):
        proc.stop_sent = now
        try:
            proc.popen.stdin.write(b"stop\n")
            proc.popen.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        log.info("account %s: stop sent", aid)

    def kill(self, aid, proc):
        try:
            proc.popen.kill()
        except OSError:
            pass
        log.warning("account %s: worker killed", aid)

    def _after_exit(self, st, code, proc, now):
        st.pid, st.heartbeat_at = None, None
        if proc.log_file:
            proc.log_file.close()
        if st.desired == "stopped":
            st.status = "stopped"
            if code != EXIT_STOPPED:
                st.reason = None
            return
        if code in NO_RETRY:
            st.desired = "stopped"
            st.status = "stopped" if code == EXIT_STOPPED else "error"
            st.reason = st.reason or EXIT_TEXT.get(code)
            st.retries = 0
            return
        if code == EXIT_LOCKED:
            st.status, st.next_retry_at = "starting", now + dt.timedelta(seconds=5)
            return
        if code == EXIT_DETACHED:
            st.status, st.next_retry_at = "starting", now
            return
        st.retries += 1
        st.status = "error"
        st.reason = st.reason or "The bot process stopped unexpectedly (exit code %s)." % code
        st.next_retry_at = now + dt.timedelta(seconds=backoff(st.retries))
        log.warning("account %s: worker exited with %s, retry %d in %ss", st.account_id, code, st.retries,
                    backoff(st.retries))

    # -- one pass
    def step(self, now=None):
        now = now or utcnow()
        with session() as s:
            states = {st.account_id: st for st in s.scalars(select(BotState))}
            for aid, proc in list(self.procs.items()):
                code = proc.popen.poll()
                if code is None:
                    continue
                del self.procs[aid]
                if aid in states:
                    s.refresh(states[aid])         # the worker may have just written its reason
                    self._after_exit(states[aid], code, proc, now)
            for aid, proc in self.procs.items():
                st = states.get(aid)
                if st is None or st.desired == "stopped":
                    if proc.stop_sent is None:
                        self.send_stop(aid, proc, now)
                        if st is not None:
                            st.status = "stopping"
                    elif (now - proc.stop_sent).total_seconds() > STOP_TIMEOUT:
                        self.kill(aid, proc)
                    continue
                age = (now - proc.started).total_seconds()
                silent = (now - st.heartbeat_at).total_seconds() if st.heartbeat_at else None
                if (silent is not None and silent > HEARTBEAT_TIMEOUT) or (silent is None and age > BOOT_TIMEOUT):
                    st.reason = ("The bot stopped responding." if silent is not None
                                 else "The bot did not finish starting in time.")
                    self.kill(aid, proc)
                elif st.retries and st.status == "running" and age > HEALTHY_RESET:
                    st.retries = 0
            for aid, st in states.items():
                if st.desired == "running" and aid not in self.procs:
                    if st.next_retry_at and st.next_retry_at > now:
                        continue
                    self.spawn(s, st, now)
            s.commit()
        if self._pruned is None or (now - self._pruned).total_seconds() > 86400:
            self.prune(now)

    def prune(self, now):
        self._pruned = now
        with session() as s:
            s.execute(delete(AccountEvent).where(AccountEvent.at < now - dt.timedelta(days=EVENT_DAYS)))
            s.commit()

    def restore(self):
        """At start: no worker of ours exists yet. Bots the user left running are started by the
        first step(); a stop that was cut off by a restart is reported."""
        with session() as s:
            for st in s.scalars(select(BotState)):
                if st.desired == "running":
                    st.next_retry_at, st.pid = None, None
                    st.status = "starting"
                elif st.status in ("running", "starting", "stopping"):
                    st.status, st.pid = "stopped", None
                    st.reason = "The server restarted while this bot was stopping. Check open trades in MT5."
            s.commit()

    def detach_all(self):
        """Server shutdown: workers stop analysing and leave trades alone; restore() brings them back."""
        for aid, proc in self.procs.items():
            try:
                proc.popen.stdin.close()
            except OSError:
                pass
        deadline = time.time() + 20
        for proc in self.procs.values():
            try:
                proc.popen.wait(max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                proc.popen.kill()


def main():
    redact.install()
    cfg = get_config()
    init_db()
    lock = FileLock(cfg.data_dir / "supervisor.lock")
    if not lock.acquire():
        print("another supervisor is already running", file=sys.stderr)
        return 1
    sup = Supervisor()
    sup.restore()
    stopping = []

    def _stop(*_):
        stopping.append(True)
    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    log.info("supervisor running (connector: %s)", cfg.connector)
    try:
        while not stopping:
            try:
                sup.step()
            except Exception:
                log.exception("supervisor step failed")
            time.sleep(1)
    finally:
        sup.detach_all()
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
