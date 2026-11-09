import logging

import pytest

from conftest import BROKER_PASSWORD, account_body, csrf, new_user


def test_password_encryption_round_trip_and_binding():
    from mohz.crypto import CryptoError, decrypt_password, encrypt_password
    blob = encrypt_password("pw-123", 1, 2)
    assert b"pw-123" not in blob
    assert decrypt_password(blob, 1, 2) == "pw-123"
    with pytest.raises(CryptoError):            # copied to another account
        decrypt_password(blob, 1, 3)
    with pytest.raises(CryptoError):            # another user
        decrypt_password(blob, 9, 2)
    with pytest.raises(CryptoError):            # another key
        decrypt_password(blob, 1, 2, keys={1: b"z" * 32})
    assert encrypt_password("pw-123", 1, 2) != blob        # random nonce


def test_redaction():
    from mohz.redact import redact
    assert "hunter2" not in redact('login with {"password": "hunter2"}')
    assert "hunter2" not in redact("password=hunter2&x=1")
    assert "abc.def" not in redact("Authorization: Bearer abc.def")
    assert "AAAA" not in redact("https://api.telegram.org/bot123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/send")


def test_log_filter_scrubs_records(caplog):
    from mohz.redact import RedactingFilter
    log = logging.getLogger("mohz.test")
    log.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO):
        log.info("connecting with password=%s", "hunter2")
    assert "hunter2" not in caplog.text


def test_register_login_logout_and_cookie_flags(client):
    email = new_user(client)
    assert client.get("/api/me").status_code == 200
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 200
    raw = r.headers.get_list("set-cookie")
    sess = next(c for c in raw if c.startswith("mohz_session="))
    assert "HttpOnly" in sess and "SameSite=lax" in sess


def test_user_password_is_hashed(client):
    email = new_user(client)
    from sqlalchemy import select
    from mohz.db import session
    from mohz.models import User
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        assert u.password_hash.startswith("$argon2")
        assert "correct horse" not in u.password_hash


def test_login_rate_limit(client):
    email = new_user(client)
    client.post("/api/auth/logout")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": email, "password": "nope-nope-nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 429


def test_csrf_required_on_writes(client):
    new_user(client)
    assert client.patch("/api/me", json={"name": "X"}).status_code == 403
    assert client.patch("/api/me", json={"name": "X"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.patch("/api/me", json={"name": "X"}, headers=csrf(client)).status_code == 200


def test_broker_password_never_returned(client):
    new_user(client)
    r = client.post("/api/accounts", json=account_body(), headers=csrf(client))
    assert r.status_code == 200, r.text
    acct = r.json()["account"]
    assert acct["password_set"] is True
    bodies = [r.text, client.get("/api/accounts").text, client.get("/api/accounts/%d/settings" % acct["id"]).text,
              client.get("/api/accounts/%d/events" % acct["id"]).text]
    from mohz.db import session
    from mohz.models import BrokerAccount
    with session() as s:
        blob = s.get(BrokerAccount, acct["id"]).password_enc
    for b in bodies:
        assert BROKER_PASSWORD not in b
        assert "password_enc" not in b
        assert blob.hex() not in b
    assert BROKER_PASSWORD.encode() not in blob


def test_accounts_are_private_to_their_owner(client):
    new_user(client)
    aid = client.post("/api/accounts", json=account_body(), headers=csrf(client)).json()["account"]["id"]
    client.post("/api/auth/logout")
    new_user(client)          # someone else
    h = csrf(client)
    assert client.get("/api/accounts").json()["accounts"] == []
    for method, path, body in [("patch", "", {"nickname": "mine now"}), ("delete", "", None),
                               ("post", "/start", None), ("post", "/stop", None), ("get", "/settings", None),
                               ("put", "/settings", {}), ("get", "/events", None)]:
        kw = {"headers": h}
        if body is not None:
            kw["json"] = body
        r = getattr(client, method)("/api/accounts/%d%s" % (aid, path), **kw)
        assert r.status_code == 404, (method, path, r.status_code)
    r = client.post("/api/accounts/detect", json={"server": "x", "login": "1", "symbol": "XAUUSD",
                                                  "account_id": aid}, headers=h)
    assert r.status_code == 404


def test_unauthenticated_is_rejected(client):
    client.cookies.clear()
    for path in ("/api/accounts", "/api/payments", "/api/me", "/api/stream"):
        assert client.get(path).status_code == 401
