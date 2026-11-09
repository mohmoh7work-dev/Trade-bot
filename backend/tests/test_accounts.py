from conftest import account_body, csrf, new_user


def test_add_account_logs_in_and_detects_contract(client):
    new_user(client)
    r = client.post("/api/accounts", json=account_body(server="JustMarkets-Demo", symbol="XAUUSD"),
                    headers=csrf(client))
    assert r.status_code == 200, r.text
    a = r.json()["account"]
    assert a["symbol"] == "XAUUSD.m"          # the broker's own name, found at login
    assert a["account_type"] == "demo"
    assert a["bot"]["status"] == "stopped"
    assert a["settings"]["close_on_stop"] is True


def test_wrong_password_shows_broker_error_and_is_not_saved(client):
    new_user(client)
    r = client.post("/api/accounts", json=account_body(password="wrong-pass"), headers=csrf(client))
    assert r.status_code == 400
    assert "Authorization failed" in r.json()["detail"]
    assert client.get("/api/accounts").json()["accounts"] == []


def test_detect_symbol(client):
    new_user(client)
    r = client.post("/api/accounts/detect", json={"server": "Exness-MT5Trial", "login": "123", "password": "x1",
                                                  "symbol": "XAUUSD"}, headers=csrf(client))
    assert r.status_code == 200, r.text
    assert r.json()["symbol"] == "XAUUSDm"


def test_duplicate_broker_login_rejected(client):
    new_user(client)
    body = account_body()
    assert client.post("/api/accounts", json=body, headers=csrf(client)).status_code == 200
    r = client.post("/api/accounts", json=dict(body, nickname="again"), headers=csrf(client))
    assert r.status_code == 409
    client.post("/api/auth/logout")
    new_user(client)
    r = client.post("/api/accounts", json=dict(body, server=" justmarkets-demo "), headers=csrf(client))
    assert r.status_code == 409


def test_mt4_refused(client):
    new_user(client)
    r = client.post("/api/accounts", json=account_body(platform="MT4"), headers=csrf(client))
    assert r.status_code == 422


def test_real_money_needs_allow_and_confirmation(client):
    new_user(client)
    h = csrf(client)
    r = client.post("/api/accounts", json=account_body(server="Broker-Real"), headers=h)
    assert r.status_code == 400 and r.json()["code"] == "real_account"
    r = client.post("/api/accounts", json=account_body(server="Broker-Real", allow_live=True), headers=h)
    assert r.status_code == 422          # no typed confirmation
    r = client.post("/api/accounts", json=account_body(server="Broker-Real", allow_live=True, confirm_text="LIVE",
                                                       confirm_password="not my password"), headers=h)
    assert r.status_code == 403
    r = client.post("/api/accounts", json=account_body(server="Broker-Real", allow_live=True, confirm_text="LIVE",
                                                       confirm_password="correct horse battery"), headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["account"]["account_type"] == "real"


def test_start_stop_and_edit_rules(client):
    new_user(client)
    h = csrf(client)
    a = client.post("/api/accounts", json=account_body(), headers=h).json()["account"]
    r = client.post("/api/accounts/%d/start" % a["id"], headers=h)
    assert r.json()["account"]["bot"]["status"] == "starting"
    assert r.json()["account"]["bot"]["desired"] == "running"
    # the login cannot change under a running bot; the nickname and mode can
    r = client.patch("/api/accounts/%d" % a["id"], json={"password": "new-password"}, headers=h)
    assert r.status_code == 409
    r = client.patch("/api/accounts/%d" % a["id"], json={"nickname": "Renamed", "mode": "auto"}, headers=h)
    assert r.status_code == 200 and r.json()["account"]["mode"] == "auto"
    r = client.post("/api/accounts/%d/stop" % a["id"], headers=h)
    assert r.json()["account"]["bot"]["status"] == "stopped"
    ev = client.get("/api/accounts/%d/events" % a["id"]).json()["events"]
    assert [e["message"] for e in ev][:2] == ["Stop requested (closing open trades).", "Start requested."]


def test_edit_password_relogs_in(client):
    new_user(client)
    h = csrf(client)
    a = client.post("/api/accounts", json=account_body(), headers=h).json()["account"]
    r = client.patch("/api/accounts/%d" % a["id"], json={"password": "wrong-new"}, headers=h)
    assert r.status_code == 400
    r = client.patch("/api/accounts/%d" % a["id"], json={"password": "a-better-one"}, headers=h)
    assert r.status_code == 200


def test_settings_validation_and_mapping(client):
    new_user(client)
    h = csrf(client)
    a = client.post("/api/accounts", json=account_body(), headers=h).json()["account"]
    url = "/api/accounts/%d/settings" % a["id"]
    lim = client.get(url).json()["limits"]
    assert lim["risk_pct"] == 2.0 and lim["max_open_trades"] == 3
    assert client.put(url, json={"risk_pct": 5}, headers=h).status_code == 422          # over the hard limit
    assert client.put(url, json={"trading_hours": [{"from": "25:00", "to": "26:00"}]}, headers=h).status_code == 422
    good = {"sizing": "lot", "lot": 0.05, "max_open_trades": 2, "max_spread": 0.5, "daily_loss_pct": 2,
            "max_drawdown_pct": 8, "trading_hours": [{"from": "08:30", "to": "11:30"}], "close_on_stop": False}
    r = client.put(url, json=good, headers=h)
    assert r.status_code == 200, r.text

    from mohz.db import session
    from mohz.models import BrokerAccount
    from mohz.settings_map import engine_patch
    with session() as s:
        acct = s.get(BrokerAccount, a["id"])
        p = engine_patch(acct)
        assert acct.settings_version == 2
    assert p["mode"] == "alerts" and p["account"] == "demo" and p["confirm_each_trade"] is False
    assert p["risk"]["mode"] == "fixed_lot" and p["risk"]["fixed_lot"] == 0.05
    assert p["risk"]["max_open_trades"] == 2 and p["exits"]["max_spread"] == 0.5
    assert p["filters"]["custom_hours"] == [{"from": "08:30", "to": "11:30"}]
    assert not any(p["filters"]["sessions"].values())


def test_delete_account(client):
    new_user(client)
    h = csrf(client)
    a = client.post("/api/accounts", json=account_body(), headers=h).json()["account"]
    assert client.delete("/api/accounts/%d" % a["id"], headers=h).status_code == 200
    assert client.get("/api/accounts").json()["accounts"] == []


def test_payments_empty_and_account_details(client):
    email = new_user(client)
    h = csrf(client)
    assert client.get("/api/payments").json() == {"payments": []}
    me = client.get("/api/me").json()["user"]
    assert me["email"] == email and me["plan"]["name"] == "Free"
    assert client.post("/api/me/password", json={"current_password": "bad", "new_password": "x" * 12},
                       headers=h).status_code == 403
    assert client.post("/api/me/password", json={"current_password": "correct horse battery",
                                                 "new_password": "short"}, headers=h).status_code == 422
    assert client.post("/api/me/password", json={"current_password": "correct horse battery",
                                                 "new_password": "a new long password"}, headers=h).status_code == 200
    assert client.request("DELETE", "/api/me", json={"password": "a new long password"}, headers=h).status_code == 200
    assert client.get("/api/me").status_code == 401
