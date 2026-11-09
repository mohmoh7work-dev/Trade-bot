"""How a process reaches MetaTrader 5.

- "mt5" (production, Windows): the MetaTrader5 package. The package talks to one terminal
  per process, so every broker account gets its own portable copy of the terminal
  (MOHZ_TERMINALS_DIR/<account id>/terminal64.exe), copied once from MOHZ_MT5_TEMPLATE_DIR.
  Login checks use a few spare copies (_probe_1, _probe_2...).
- "fake" (development, any OS): a simulated broker with moving gold prices.
"""
import shutil
from pathlib import Path

from ..config import get_config

TERMINAL_EXE = "terminal64.exe"


class ConnectorError(Exception):
    pass


def load_mt5():
    cfg = get_config()
    if cfg.connector == "fake":
        from .fake import FakeLiveMT5
        return FakeLiveMT5()
    if cfg.connector != "mt5":
        raise ConnectorError("unknown MOHZ_CONNECTOR %r (mt5 or fake)" % cfg.connector)
    try:
        import MetaTrader5 as mt5  # noqa: N813  (Windows only)
    except ImportError as e:
        raise ConnectorError("the MetaTrader5 package is not installed (Windows only: pip install MetaTrader5)") from e
    return mt5


def terminal_path(name):
    """Path of the terminal for one account (or probe slot), copying the template the first time."""
    cfg = get_config()
    if cfg.connector != "mt5":
        return ""
    dest = cfg.terminals_dir / str(name)
    exe = dest / TERMINAL_EXE
    if exe.exists():
        return str(exe)
    tpl = Path(cfg.mt5_template_dir) if cfg.mt5_template_dir else None
    if not tpl or not (tpl / TERMINAL_EXE).exists():
        raise ConnectorError("MOHZ_MT5_TEMPLATE_DIR must point to a portable MetaTrader 5 folder with %s"
                             % TERMINAL_EXE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Logs, history caches and saved accounts are per terminal: never copy them from the template.
    shutil.copytree(tpl, dest, ignore=shutil.ignore_patterns("logs", "Logs", "bases", "Bases", "*.log",
                                                             "accounts.dat", "Config/accounts.dat"))
    return str(exe)


def remove_terminal(name):
    cfg = get_config()
    dest = cfg.terminals_dir / str(name)
    if cfg.connector == "mt5" and dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
