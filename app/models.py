"""Persistent application data.

Note what is deliberately *absent*: there is no column anywhere here for a face
encoding or an uploaded image. Biometric templates live only in memory for the
duration of a single scan (see :mod:`app.recognition`). What persists is the
*governance metadata* — who we hold a consent basis on file for, and until when —
not the biometric itself.
"""

from __future__ import annotations

from flask_login import UserMixin

from app import db
from app.governance.policy import ConsentStatus, Individual
from app.governance.retention import default_expiry


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    # Werkzeug hashes can exceed 150 chars (e.g. scrypt); size generously.
    password = db.Column(db.String(255), nullable=False)


class ConsentRecord(db.Model):
    """A durable record of the consent basis on file for one individual.

    Holds no biometric data — only the operator-facing label, the consent
    status, the lawful basis text, and the retention window after which even
    this metadata is purged.
    """

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    consent_status = db.Column(db.String(20), nullable=False, default=ConsentStatus.UNKNOWN.value)
    lawful_basis = db.Column(db.String(500), nullable=False, default="")
    enrolled_at = db.Column(db.Float, nullable=False)
    retention_expiry = db.Column(db.Float, nullable=False)

    __table_args__ = (db.UniqueConstraint("owner_id", "label", name="uq_owner_label"),)

    def to_individual(self) -> Individual:
        return Individual(
            id=str(self.id),
            label=self.label,
            consent_status=ConsentStatus(self.consent_status),
            lawful_basis=self.lawful_basis,
            enrolled_at=self.enrolled_at,
            retention_expiry=self.retention_expiry,
        )

    @staticmethod
    def make(owner_id, label, status, basis, now, retention_seconds):
        return ConsentRecord(
            owner_id=owner_id,
            label=label,
            consent_status=status.value if isinstance(status, ConsentStatus) else status,
            lawful_basis=basis,
            enrolled_at=now,
            retention_expiry=default_expiry(now, retention_seconds),
        )
