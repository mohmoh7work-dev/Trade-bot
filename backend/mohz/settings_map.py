"""The per-account settings shown on the card, and how they become engine settings.

The card's settings are a small, user-facing subset. Everything else keeps the
engine's own defaults (engine/settings.py:DEFAULTS), and the engine still clamps
every value to its HARD_LIMITS.
"""
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from .engine_bridge import hard_limits

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Window(BaseModel):
    start: str = Field(alias="from")
    end: str = Field(alias="to")

    model_config = {"populate_by_name": True}

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v):
        if not HHMM.match(v):
            raise ValueError("use HH:MM, e.g. 08:30")
        return v

    @model_validator(mode="after")
    def _order(self):
        if self.start == self.end:
            raise ValueError("a trading window cannot start and end at the same time")
        return self


class BotSettings(BaseModel):
    sizing: str = "risk"                  # risk (% of balance at the stop) | lot (fixed lot size)
    risk_pct: float = 0.5
    lot: float = 0.01
    max_open_trades: int = 1
    max_spread: float = 0.60              # price units ($ on gold)
    daily_loss_pct: float = 3.0           # auto-stops the bot
    max_drawdown_pct: float = 10.0        # auto-stops the bot (and the engine closes its trades)
    trading_hours: list[Window] = []      # New York time; empty = the engine's London + New York sessions
    close_on_stop: bool = True            # Stop bot closes the bot's open trades

    @model_validator(mode="after")
    def _limits(self):
        hl = hard_limits()
        if self.sizing not in ("risk", "lot"):
            raise ValueError("sizing must be risk or lot")
        checks = [("risk_pct", 0.01, hl["max_risk_pct"]), ("lot", 0.01, hl["max_lot"]),
                  ("max_open_trades", 1, hl["max_open_trades"]), ("max_spread", 0.01, 50.0),
                  ("daily_loss_pct", 0.1, hl["max_daily_loss_pct"]), ("max_drawdown_pct", 0.5, hl["max_drawdown_pct"])]
        for name, lo, hi in checks:
            v = getattr(self, name)
            if not lo <= v <= hi:
                raise ValueError("%s must be between %s and %s" % (name.replace("_", " "), lo, hi))
        if len(self.trading_hours) > 6:
            raise ValueError("at most 6 trading windows")
        return self

    def dump(self):
        return self.model_dump(by_alias=True)


def limits():
    """What the settings form shows as the maximums."""
    hl = hard_limits()
    return {"risk_pct": hl["max_risk_pct"], "lot": hl["max_lot"], "max_open_trades": hl["max_open_trades"],
            "daily_loss_pct": hl["max_daily_loss_pct"], "max_drawdown_pct": hl["max_drawdown_pct"]}


def load(doc):
    return BotSettings.model_validate(doc or {})


def engine_patch(account, settings=None):
    """The engine settings document for one broker account."""
    s = settings or load(account.settings)
    hl = hard_limits()
    live = bool(account.allow_live and account.account_type == "real")
    patch = {
        "symbol": account.symbol,
        "mode": "auto" if account.mode == "auto" else "alerts",
        "confirm_each_trade": False,       # Auto-trade on the dashboard = the engine executes by itself
        "account": "live" if live else "demo",
        "mt5_offset_hours": float(account.mt5_offset_hours),
        "risk": {
            "mode": "percent" if s.sizing == "risk" else "fixed_lot",
            "risk_pct": float(s.risk_pct),
            "fixed_lot": float(s.lot),
            "max_lot": min(float(hl["max_lot"]), max(0.5, float(s.lot))),
            "max_open_trades": int(s.max_open_trades),
            "daily_loss_pct": float(s.daily_loss_pct),
            "max_drawdown_pct": float(s.max_drawdown_pct),
        },
        "exits": {"max_spread": float(s.max_spread)},
    }
    if s.trading_hours:
        patch["filters"] = {"sessions": {"asia": False, "london": False, "newyork": False},
                            "custom_hours": [{"from": w.start, "to": w.end} for w in s.trading_hours]}
    return patch
