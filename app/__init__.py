"""Application factory.

Replaces the previous import-time-global setup (which hardcoded debug mode, a
possibly-None secret key, and two competing LoginManager instances). Extensions
are created once at module scope and bound to the app inside :func:`create_app`,
so the app can be configured differently for tests vs. production.

The audit store is attached to the app object as ``app.audit_store`` — a single
thread-safe, append-only ledger shared across requests.
"""

from __future__ import annotations

import os
import secrets

from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def _resolve_secret(app: Flask) -> str:
    secret = os.getenv("SECRET_KEY")
    if secret:
        return secret
    if app.config.get("TESTING"):
        return "testing-secret"
    # Dev fallback: usable but ephemeral. Loud, because a rotating secret key
    # silently invalidates sessions on every restart.
    app.logger.warning("SECRET_KEY not set — using an ephemeral dev key. Do NOT use in production.")
    return secrets.token_hex(32)


def _resolve_audit_key(app: Flask) -> bytes:
    # The audit signing key MUST be stable across restarts, or previously-written
    # entries stop verifying. Prefer an explicit env var; fall back to deriving
    # from SECRET_KEY so a configured deployment is self-consistent.
    raw = os.getenv("AUDIT_KEY")
    if raw:
        return raw.encode("utf-8")
    if not app.config.get("TESTING"):
        app.logger.warning("AUDIT_KEY not set — deriving from SECRET_KEY. Set AUDIT_KEY explicitly in production.")
    return app.config["SECRET_KEY"].encode("utf-8")


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'app.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUDIT_DB_PATH=os.path.join(app.instance_path, "audit.db"),
        # Cap uploads so a giant file can't exhaust memory during in-memory scans.
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        # Default scan threshold + retention window; both operator-tunable.
        FACE_TOLERANCE=0.6,
        RETENTION_SECONDS=90 * 24 * 60 * 60,
        # Recognition model knobs (deployment-level, never per-request — "cnn"
        # is far slower and would be a DoS vector if user-selectable).
        FACE_DETECTOR=os.getenv("FACE_DETECTOR", "hog"),
        FACE_UPSAMPLE=int(os.getenv("FACE_UPSAMPLE", "1")),
        FACE_ENCODING_MODEL=os.getenv("FACE_ENCODING_MODEL", "small"),
    )
    if config:
        app.config.update(config)
    app.config["SECRET_KEY"] = _resolve_secret(app)

    from app.recognition import validate_recognition_config

    validate_recognition_config(
        app.config["FACE_DETECTOR"],
        app.config["FACE_ENCODING_MODEL"],
        app.config["FACE_UPSAMPLE"],
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."

    from app.governance.store import AuditStore

    app.audit_store = AuditStore(app.config["AUDIT_DB_PATH"], _resolve_audit_key(app))

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):  # noqa: D401
        return db.session.get(User, int(user_id))

    from app.auth import auth_bp
    from app.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    return app
