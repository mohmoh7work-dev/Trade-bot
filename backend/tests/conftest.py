import base64
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEST_KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
BROKER_PASSWORD = "Sup3r-Secret-Broker-PW"


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    data = tmp_path_factory.mktemp("mohz-data")
    os.environ.update({
        "MOHZ_DATA_DIR": str(data),
        "MOHZ_DATABASE_URL": "sqlite:///%s" % (data / "test.db").as_posix(),
        "MOHZ_BROKER_KEY": TEST_KEY,
        "MOHZ_CONNECTOR": "fake",
        "MOHZ_COOKIE_SECURE": "false",
        "MOHZ_PROBE_SLOTS": "2",
        "MOHZ_FRONTEND_DIST": str(data / "no-frontend"),
    })
    from mohz.config import reset_config
    reset_config()
    from mohz import auth      # many users and login checks come from one test client address
    auth.LIMITS["register"] = (60, None, 100000)
    auth.LIMITS["probe"] = (10, None, 100000)
    from mohz.db import init_db
    init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from mohz.app import create_app
    with TestClient(create_app()) as c:
        yield c


_n = [0]


def new_user(client, password="correct horse battery"):
    _n[0] += 1
    email = "user%d@example.com" % _n[0]
    r = client.post("/api/auth/register", json={"name": "User %d" % _n[0], "email": email, "password": password})
    assert r.status_code == 200, r.text
    return email


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("mohz_csrf")}


_login = [50000000]


def account_body(**kw):
    _login[0] += 1
    body = {"nickname": "Gold demo", "platform": "MT5", "broker": "JustMarkets", "server": "JustMarkets-Demo",
            "login": str(_login[0]), "password": BROKER_PASSWORD, "symbol": "XAUUSD", "mode": "alerts"}
    body.update(kw)
    return body
