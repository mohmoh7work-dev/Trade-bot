"""Turns engine events into the per-account log shown on the card (kind, level, one plain line)."""


def _p(x, d=2):
    return "-" if x is None else ("%%.%df" % d) % float(x)


def _money(x):
    if x is None:
        return "-"
    return ("+" if x >= 0 else "-") + "%.2f" % abs(float(x))


SKIP = {"agent_message", "proposal", "cycle_start", "status", "settings_changed"}


def translate(kind, data, mode="auto"):
    """(kind, level, message, data) or None to skip."""
    d = data or {}
    if kind in SKIP:
        return None
    if kind == "decision":
        if d.get("action") in ("BUY", "SELL"):
            msg = "Council: %s %s lot at %s (SL %s, TP1 %s, TP2 %s), %d/%d agree, confidence %d" % (
                d["action"], _p(d.get("lots")), _p(d.get("entry")), _p(d.get("sl")), _p(d.get("tp1")),
                _p(d.get("tp2")), d.get("agreement", 0), d.get("agreement_of", 0), d.get("confidence", 0))
        else:
            msg = "Council: no trade. %s" % (d.get("reason") or "")
        return "decision", "info", msg.strip(), {k: d.get(k) for k in ("action", "entry", "sl", "tp1", "tp2", "lots",
                                                                     "confidence", "agreement", "reason")}
    if kind == "signal":
        tail = " Alert only: no order sent." if mode != "auto" else ""
        return "signal", "info", "Signal #%s: %s at %s, SL %s, TP1 %s, TP2 %s.%s" % (
            d.get("signal_id"), d.get("action"), _p(d.get("entry")), _p(d.get("sl")), _p(d.get("tp1")),
            _p(d.get("tp2")), tail), {k: d.get(k) for k in ("signal_id", "action", "entry", "sl", "tp1", "tp2", "lots")}
    if kind == "trade_opened":
        leg = " (leg %s)" % d["leg"] if d.get("leg") else ""
        return "trade", "info", "Opened %s %s lot at %s, SL %s%s" % (
            d.get("side"), _p(d.get("lots")), _p(d.get("open_price")), _p(d.get("sl")), leg), d
    if kind in ("trade_closed", "trade_partial"):
        what = "Closed" if kind == "trade_closed" else "Partly closed"
        return "trade", "info", "%s %s %s lot at %s: %s, P/L %s" % (
            what, d.get("side"), _p(d.get("lots")), _p(d.get("price")), d.get("reason") or "closed",
            _money(d.get("pnl"))), d
    if kind == "trade_modified":
        return "trade", "info", "Stop moved to %s (%s)" % (_p(d.get("sl")), d.get("why") or "update"), d
    if kind == "order_skipped":
        return "order", "warning", "Order for signal #%s skipped: %s" % (
            d.get("signal_id"), "; ".join(d.get("reasons") or [])), d
    if kind == "signal_outcome":
        return "signal", "info", "Signal #%s finished: %s (%sR)" % (d.get("signal_id"), d.get("outcome"),
                                                                    d.get("outcome_r")), d
    if kind == "error":
        return "error", "error", "%s: %s" % (d.get("where") or "engine", d.get("message") or ""), d
    if kind == "kill_switch":
        return "error", "critical", "Kill switch: %s (%s position(s) closed)" % (d.get("reason"), d.get("closed")), d
    if kind == "log":
        lvl = d.get("level") or "info"
        if lvl in ("warning", "error", "critical") or d.get("source") in ("execution", "kill_switch", "broker"):
            return "log", lvl, "%s: %s" % (d.get("source"), d.get("message")), None
        return None
    return None
