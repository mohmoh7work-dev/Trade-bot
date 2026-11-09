"""A logging filter that blanks out anything that looks like a secret.

Installed on the root logger by the API, the supervisor and the workers. The
code never logs credentials on purpose; this is the safety net.
"""
import logging
import re

_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-~+/=]+", re.I),
    re.compile(r'("?(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|mohz_session|mohz_csrf)"?\s*[:=]\s*)'
               r'("[^"]*"|\'[^\']*\'|[^\s,;}&]+)', re.I),
    re.compile(r"(bot)\d{6,}:[A-Za-z0-9_\-]{20,}"),     # Telegram bot tokens in URLs
]


def redact(text):
    if not isinstance(text, str):
        return text
    for p in _PATTERNS:
        text = p.sub(lambda m: m.group(1) + "***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:   # a bad format string: let logging report it
            return True
        clean = redact(msg)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


def install(level=logging.INFO):
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    f = RedactingFilter()
    for h in root.handlers:
        h.addFilter(f)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            h.addFilter(f)
