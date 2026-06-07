"""Tests for the persistent, append-only AuditStore."""

import sqlite3

import pytest

from app.governance import ledger
from app.governance.store import AuditStore

KEY = b"store-test-key"


class FakeClock:
    """Deterministic, advancing clock for reproducible timestamps."""

    def __init__(self, start=1000.0, step=1.0):
        self.now = start
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


def make_store(tmp_path, clock=None):
    return AuditStore(str(tmp_path / "audit.db"), KEY, clock=clock or FakeClock())


def test_append_assigns_contiguous_seq_and_links(tmp_path):
    store = make_store(tmp_path)
    e0 = store.append("alice", "enroll_face", {"individual_id": "ind-1"})
    e1 = store.append("alice", "scan_batch", {"photos": 3, "matches": 1})
    assert e0["seq"] == 0 and e1["seq"] == 1
    assert e0["prev_hmac"] == ledger.GENESIS_HMAC
    assert e1["prev_hmac"] == e0["hmac"]
    assert store.verify() is True


def test_store_requires_key(tmp_path):
    with pytest.raises(ValueError):
        AuditStore(str(tmp_path / "x.db"), b"")


def test_chain_survives_reopen(tmp_path):
    path = tmp_path / "audit.db"
    s1 = AuditStore(str(path), KEY, clock=FakeClock())
    s1.append("alice", "enroll_face", {"individual_id": "ind-1"})
    s1.append("system", "purge_expired", {"removed": 0})
    s1.close()
    # Reopen and keep appending — linkage must continue from persisted state.
    s2 = AuditStore(str(path), KEY, clock=FakeClock(start=2000.0))
    e2 = s2.append("alice", "scan_batch", {"photos": 5, "matches": 2})
    assert e2["seq"] == 2
    assert s2.verify() is True


def test_clock_running_backwards_is_clamped(tmp_path):
    # Even with a clock that jumps backwards, ts must be non-decreasing.
    store = AuditStore(str(tmp_path / "audit.db"), KEY, clock=FakeClock(start=1000.0, step=-50.0))
    store.append("a", "one", {})
    store.append("a", "two", {})
    store.append("a", "three", {})
    tss = [e["ts"] for e in store.entries()]
    assert tss == sorted(tss)
    assert store.verify() is True


def test_direct_db_edit_is_detected(tmp_path):
    path = tmp_path / "audit.db"
    store = make_store(tmp_path)
    store.append("alice", "scan_batch", {"photos": 12, "matches": 2})
    store.append("alice", "scan_batch", {"photos": 4, "matches": 0})
    store.close()
    # Simulate an attacker with raw DB access rewriting a recorded match count.
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE audit SET payload_json = ? WHERE seq = 0", ('{"matches":0,"photos":12}',))
    conn.commit()
    conn.close()
    reopened = AuditStore(str(path), KEY)
    with pytest.raises(ledger.ChainError) as exc:
        reopened.verify()
    assert exc.value.seq == 0
    assert "payload" in exc.value.reason


def test_export_round_trips_through_pure_verifier(tmp_path):
    store = make_store(tmp_path)
    for i in range(5):
        store.append("alice", "scan_batch", {"photos": i, "matches": i % 2})
    # The exported entries verify under the pure, app-independent core too.
    assert ledger.verify_chain(KEY, store.entries()) is True
