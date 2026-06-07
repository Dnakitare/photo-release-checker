"""Integration tests for the app factory, auth, and the audit-trail screen.

These don't touch dlib — they cover the governance/web wiring: registration,
login gating, the duplicate-username fix, and that privacy-relevant actions land
in a verifiable audit ledger.
"""

from tests.conftest import login, register


def test_register_creates_user_and_audit_entry(app, client):
    resp = register(client)
    assert b"Please log in" in resp.data
    # Registration is recorded in the ledger, which still verifies.
    assert app.audit_store.verify() is True
    actions = [e["action"] for e in app.audit_store.entries()]
    assert "user_registered" in actions


def test_duplicate_username_is_rejected_not_500(client):
    register(client)
    resp = register(client)  # same username again
    assert resp.status_code == 200
    assert b"already taken" in resp.data


def test_short_password_rejected(client):
    resp = client.post("/register", data={"username": "bob", "password": "short"},
                       follow_redirects=True)
    assert b"at least 8 characters" in resp.data


def test_protected_routes_require_login(client):
    for path in ("/", "/registry", "/audit"):
        resp = client.get(path, follow_redirects=True)
        assert b"Log in" in resp.data, path


def test_login_then_access_audit_screen(client):
    register(client)
    login(client)
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert b"chain verified" in resp.data  # green banner on an intact chain


def test_wrong_password_fails(client):
    register(client)
    resp = client.post("/login", data={"username": "alice", "password": "wrongpass1"},
                       follow_redirects=True)
    assert b"Invalid credentials" in resp.data


def test_registry_empty_for_new_user(client):
    register(client)
    login(client)
    resp = client.get("/registry")
    assert resp.status_code == 200
    assert b"No consent records on file" in resp.data


def test_purge_with_nothing_expired_records_zero(app, client):
    register(client)
    login(client)
    resp = client.post("/registry/purge", follow_redirects=True)
    assert b"Purged 0 expired" in resp.data
    assert app.audit_store.verify() is True
    assert "purge_expired" in [e["action"] for e in app.audit_store.entries()]
