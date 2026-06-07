"""Shared fixtures for the Flask integration tests."""

import pytest

from app import create_app, db as _db


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # exercise routes without round-tripping tokens
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'app.db'}",
        "AUDIT_DB_PATH": str(tmp_path / "audit.db"),
        "RETENTION_SECONDS": 90 * 24 * 60 * 60,
        "FACE_TOLERANCE": 0.6,
    })
    yield application
    application.audit_store.close()
    with application.app_context():
        _db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="alice", password="password123"):
    return client.post("/register", data={"username": username, "password": password},
                       follow_redirects=True)


def login(client, username="alice", password="password123"):
    return client.post("/login", data={"username": username, "password": password},
                      follow_redirects=True)
