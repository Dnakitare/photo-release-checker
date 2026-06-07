"""Retention policy: enforce that biometric metadata doesn't outlive its basis.

Data minimization isn't a one-time act — it's a schedule. Every enrolled
individual carries a ``retention_expiry``; this module decides who is past it.
The decision is pure so it can be tested against a fixed clock; the actual
deletion and the audit-log entry that records it are the caller's job (the store
deletes, the ledger remembers that a purge happened and how many records went).
"""

from __future__ import annotations

from typing import Iterable

from app.governance.policy import Individual

# Sensible default: biometric templates expire 90 days after enrollment unless
# the operator sets a shorter window. Short by design — this is the opposite of
# "collect and keep forever."
DEFAULT_RETENTION_SECONDS = 90 * 24 * 60 * 60


def is_expired(individual: Individual, now: float) -> bool:
    return individual.retention_expiry <= now


def expired(individuals: Iterable[Individual], now: float) -> list[Individual]:
    """Those whose retention window has closed as of ``now``."""
    return [ind for ind in individuals if is_expired(ind, now)]


def default_expiry(enrolled_at: float, retention_seconds: int = DEFAULT_RETENTION_SECONDS) -> float:
    """Compute an expiry timestamp from an enrollment time and a window."""
    if retention_seconds <= 0:
        raise ValueError("retention_seconds must be positive")
    return enrolled_at + retention_seconds
