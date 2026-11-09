"""Imports the trading engine from the engine-src submodule (mohmoh7work-dev/Trade), unchanged."""
import sys

from .config import get_config


def ensure_engine_path():
    src = str(get_config().engine_src)
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import engine  # noqa: F401
    except ImportError as e:
        raise SystemExit("cannot import the engine from %s: run `git submodule update --init` (%s)" % (src, e))


def hard_limits():
    ensure_engine_path()
    from engine.settings import HARD_LIMITS
    return dict(HARD_LIMITS)


def engine_defaults():
    ensure_engine_path()
    from engine.settings import DEFAULTS
    return DEFAULTS
