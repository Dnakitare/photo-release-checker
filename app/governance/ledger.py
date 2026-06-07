"""Tamper-evident, append-only audit ledger.

The governance centerpiece of this app: every privacy-relevant action (enroll a
face, run a scan, purge expired data) is recorded as a link in an HMAC-chained
ledger. Each entry commits to the one before it, so any insertion, deletion, or
edit anywhere in the history invalidates every entry from that point forward.

This module is deliberately pure: no Flask, no database, no clock of its own.
It serializes deterministically and computes/verifies HMACs over plain dicts, so
the exact same logic can run inside the web app, inside a test, or inside a
standalone verifier that a third party runs against an exported log (see
``tools/verify_audit.py``). The caller supplies the sequence number and
timestamp; the store layer owns those concerns.

Design mirrors the Mavryn audit chain: HMAC + monotonicity, independently
re-derivable from an export.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

# prev_hmac value for the first (genesis) entry — nothing precedes it.
GENESIS_HMAC = "0" * 64

# Fields, in order, that an entry commits to. ``hmac`` is derived from these and
# is therefore not itself part of the signed body.
_SIGNED_FIELDS = ("seq", "ts", "actor", "action", "payload_digest", "prev_hmac")


def canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace.

    Two structurally equal payloads always produce byte-identical output, which
    is what makes the digests and HMACs reproducible across processes.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_digest(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical payload.

    The ledger stores the digest, not the raw payload, so the signed body stays
    small and so sensitive details can be omitted from the chain itself while
    still being committed to.
    """
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _signed_body(entry: dict[str, Any]) -> str:
    return canonical({k: entry[k] for k in _SIGNED_FIELDS})


def compute_hmac(key: bytes, entry: dict[str, Any]) -> str:
    """HMAC-SHA256 of an entry's signed body."""
    return hmac.new(key, _signed_body(entry).encode("utf-8"), hashlib.sha256).hexdigest()


def make_entry(
    key: bytes,
    *,
    seq: int,
    ts: float,
    actor: str,
    action: str,
    payload: dict[str, Any],
    prev_hmac: str,
) -> dict[str, Any]:
    """Build a fully-formed, signed ledger entry.

    The caller owns ``seq`` (monotonic, contiguous from 0), ``ts`` (a wall-clock
    seconds value that must be non-decreasing), and ``prev_hmac`` (the ``hmac``
    of the previous entry, or :data:`GENESIS_HMAC` for the first).
    """
    entry = {
        "seq": seq,
        "ts": ts,
        "actor": actor,
        "action": action,
        "payload_digest": payload_digest(payload),
        "prev_hmac": prev_hmac,
    }
    entry["hmac"] = compute_hmac(key, entry)
    return entry


class ChainError(ValueError):
    """Raised when a ledger fails verification, with the offending sequence."""

    def __init__(self, seq: int, reason: str):
        self.seq = seq
        self.reason = reason
        super().__init__(f"audit chain broken at seq={seq}: {reason}")


def verify_chain(key: bytes, entries: list[dict[str, Any]]) -> bool:
    """Validate an ordered ledger end to end.

    Checks, for every entry: contiguous monotonic ``seq`` starting at 0,
    non-decreasing ``ts``, correct linkage to the prior ``hmac``, and a
    recomputed ``hmac`` that matches what's stored. Raises :class:`ChainError`
    on the first violation; returns ``True`` if the whole chain is intact. An
    empty ledger is vacuously valid.
    """
    prev_hmac = GENESIS_HMAC
    prev_ts = float("-inf")
    for i, entry in enumerate(entries):
        seq = entry.get("seq")
        if seq != i:
            raise ChainError(i, f"expected seq={i}, found {seq!r}")
        if entry.get("ts", float("-inf")) < prev_ts:
            raise ChainError(i, "timestamp went backwards")
        if entry.get("prev_hmac") != prev_hmac:
            raise ChainError(i, "prev_hmac does not match previous entry")
        expected = compute_hmac(key, entry)
        if not hmac.compare_digest(expected, str(entry.get("hmac", ""))):
            raise ChainError(i, "hmac mismatch (entry was altered)")
        prev_hmac = entry["hmac"]
        prev_ts = entry["ts"]
    return True
