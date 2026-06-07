"""Tests for the retention policy decisions (pure, fixed-clock)."""

import pytest

from app.governance.policy import ConsentStatus, Individual
from app.governance import retention


def ind(id_, expiry):
    return Individual(
        id=id_,
        label=id_,
        consent_status=ConsentStatus.DECLINED,
        lawful_basis="test",
        enrolled_at=0.0,
        retention_expiry=expiry,
    )


def test_expired_partitions_by_clock():
    people = [ind("a", 100.0), ind("b", 200.0), ind("c", 300.0)]
    due = retention.expired(people, now=200.0)
    # expiry <= now counts as expired, so a and b are due; c survives.
    assert {p.id for p in due} == {"a", "b"}


def test_is_expired_boundary_is_inclusive():
    assert retention.is_expired(ind("a", 100.0), now=100.0) is True
    assert retention.is_expired(ind("a", 100.0), now=99.9) is False


def test_default_expiry_adds_window():
    assert retention.default_expiry(1000.0, retention_seconds=60) == 1060.0


def test_default_expiry_rejects_nonpositive_window():
    with pytest.raises(ValueError):
        retention.default_expiry(1000.0, retention_seconds=0)


def test_default_window_is_ninety_days():
    assert retention.DEFAULT_RETENTION_SECONDS == 90 * 24 * 60 * 60
