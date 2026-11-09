"""Live updates for the dashboard: Server-Sent Events with the user's accounts (status, balance,
equity, today's P/L, positions) whenever something changes. The browser's EventSource sends
the session cookie and reconnects by itself."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..auth import session_from_request
from ..db import session
from ..models import User
from .common import accounts_for

router = APIRouter(prefix="/api", tags=["stream"])
INTERVAL = 2.0
KEEPALIVE = 15.0


def _snapshot(sess_id_cookie_request):
    with session() as db:
        sess = session_from_request(db, sess_id_cookie_request)
        if sess is None:
            return None
        user = db.get(User, sess.user_id)
        if user is None:
            return None
        return accounts_for(db, user)


@router.get("/stream")
async def stream(request: Request):
    first = await asyncio.to_thread(_snapshot, request)
    if first is None:
        raise HTTPException(401, "Please log in.")

    async def gen():
        last, quiet = None, 0.0
        data = first
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                return
            if data is None:
                yield "event: logout\ndata: {}\n\n"
                return
            doc = json.dumps(data, sort_keys=True)
            if doc != last:
                last, quiet = doc, 0.0
                yield "event: accounts\ndata: %s\n\n" % doc
            elif quiet >= KEEPALIVE:
                quiet = 0.0
                yield ": keepalive\n\n"
            await asyncio.sleep(INTERVAL)
            quiet += INTERVAL
            data = await asyncio.to_thread(_snapshot, request)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
