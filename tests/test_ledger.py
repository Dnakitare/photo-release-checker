"""Tests for the tamper-evident audit ledger core.

These exercise the pure chain logic with a fixed key and explicit, monotonic
timestamps — no Flask, no DB, no real clock — so they're fast and deterministic.
"""

import pytest

from app.governance import ledger

KEY = b"test-key-do-not-use-in-prod"


def build_chain(events):
    """Helper: turn a list of (actor, action, payload) into a signed chain."""
    entries = []
    prev = ledger.GENESIS_HMAC
    for i, (actor, action, payload) in enumerate(events):
        entry = ledger.make_entry(
            KEY,
            seq=i,
            ts=float(1000 + i),  # strictly increasing, deterministic
            actor=actor,
            action=action,
            payload=payload,
            prev_hmac=prev,
        )
        entries.append(entry)
        prev = entry["hmac"]
    return entries


SAMPLE = [
    ("alice", "enroll_face", {"individual_id": "ind-1", "basis": "declined_release"}),
    ("alice", "scan_batch", {"photos": 12, "matches": 2}),
    ("system", "purge_expired", {"removed": 1}),
]


def test_canonical_is_order_independent():
    a = ledger.canonical({"b": 1, "a": 2})
    b = ledger.canonical({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_payload_digest_is_stable_and_sensitive():
    d1 = ledger.payload_digest({"photos": 12, "matches": 2})
    d2 = ledger.payload_digest({"matches": 2, "photos": 12})
    assert d1 == d2  # key order doesn't matter
    assert d1 != ledger.payload_digest({"photos": 12, "matches": 3})  # value does


def test_valid_chain_verifies():
    assert ledger.verify_chain(KEY, build_chain(SAMPLE)) is True


def test_empty_chain_is_vacuously_valid():
    assert ledger.verify_chain(KEY, []) is True


def test_genesis_links_to_sentinel():
    chain = build_chain(SAMPLE)
    assert chain[0]["prev_hmac"] == ledger.GENESIS_HMAC


def test_tampered_payload_is_detected():
    chain = build_chain(SAMPLE)
    # Attacker edits a recorded value but can't re-sign without the key.
    chain[1]["payload_digest"] = ledger.payload_digest({"photos": 12, "matches": 0})
    with pytest.raises(ledger.ChainError) as exc:
        ledger.verify_chain(KEY, chain)
    assert exc.value.seq == 1
    assert "hmac mismatch" in exc.value.reason


def test_deleted_entry_breaks_linkage():
    chain = build_chain(SAMPLE)
    del chain[1]  # drop the middle link; reindex to keep seq contiguous
    for new_seq, entry in enumerate(chain):
        entry["seq"] = new_seq
    with pytest.raises(ledger.ChainError) as exc:
        ledger.verify_chain(KEY, chain)
    # seq 0 still links to genesis; the break shows at the now-orphaned seq 1.
    assert exc.value.seq == 1
    assert "prev_hmac" in exc.value.reason


def test_reordered_entries_are_detected():
    chain = build_chain(SAMPLE)
    chain[1], chain[2] = chain[2], chain[1]
    chain[1]["seq"], chain[2]["seq"] = 1, 2
    with pytest.raises(ledger.ChainError):
        ledger.verify_chain(KEY, chain)


def test_backwards_timestamp_is_rejected():
    chain = build_chain(SAMPLE)
    chain[2]["ts"] = chain[1]["ts"] - 5
    chain[2]["hmac"] = ledger.compute_hmac(KEY, chain[2])  # re-sign so only ts is wrong
    with pytest.raises(ledger.ChainError) as exc:
        ledger.verify_chain(KEY, chain)
    assert exc.value.seq == 2
    assert "backwards" in exc.value.reason


def test_wrong_key_fails_verification():
    chain = build_chain(SAMPLE)
    with pytest.raises(ledger.ChainError):
        ledger.verify_chain(b"a-different-key", chain)


def test_non_contiguous_seq_is_rejected():
    chain = build_chain(SAMPLE)
    chain[2]["seq"] = 5
    chain[2]["hmac"] = ledger.compute_hmac(KEY, chain[2])
    with pytest.raises(ledger.ChainError) as exc:
        ledger.verify_chain(KEY, chain)
    assert exc.value.seq == 2
