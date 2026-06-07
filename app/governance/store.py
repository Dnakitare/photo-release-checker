"""Persistent, append-only home for the audit ledger.

The ledger lives in its own SQLite file, *separate from the application
database*. That separation is the point: the app's tables are mutable
(users register, rosters change), but the audit log must only ever grow. Giving
it a dedicated store means the code path that records history has no UPDATE or
DELETE statements at all — the only verb is INSERT.

The store owns the two things the pure ledger refuses to: the monotonic sequence
number and the clock. It clamps time forward (never backwards) so a machine with
a slipping clock can't produce a chain that fails its own monotonicity check.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Callable

from app.governance import ledger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    seq            INTEGER PRIMARY KEY,
    ts             REAL    NOT NULL,
    actor          TEXT    NOT NULL,
    action         TEXT    NOT NULL,
    payload_digest TEXT    NOT NULL,
    prev_hmac      TEXT    NOT NULL,
    hmac           TEXT    NOT NULL,
    payload_json   TEXT    NOT NULL
);
"""


class AuditStore:
    """Append-only audit ledger backed by a dedicated SQLite database."""

    def __init__(self, db_path: str, key: bytes, clock: Callable[[], float] = time.time):
        if not key:
            raise ValueError("AuditStore requires a non-empty signing key")
        self._key = key
        self._clock = clock
        # isolation_level=None puts us in autocommit mode so we can drive
        # transactions explicitly with BEGIN IMMEDIATE — that acquires SQLite's
        # write lock up front, serializing the read-last-then-insert across
        # *processes* (e.g. multiple gunicorn workers), not just threads. WAL
        # keeps concurrent readers (the audit screen) from blocking. The
        # in-process lock still guards the shared connection object itself.
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)

    def _last(self) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT seq, ts, hmac FROM audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()

    def append(self, actor: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Record one event and return the signed entry.

        The payload is stored verbatim alongside its digest so a verifier can
        confirm the digest matches — but callers must keep biometric material
        (face encodings, raw images) out of it. Only counts, ids, and decisions
        belong in the log.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")  # take the write lock before reading
            try:
                last = self._last()
                seq = 0 if last is None else last["seq"] + 1
                prev_hmac = ledger.GENESIS_HMAC if last is None else last["hmac"]
                # Clamp the clock forward so ts is never less than the previous entry.
                ts = self._clock()
                if last is not None and ts < last["ts"]:
                    ts = last["ts"]

                entry = ledger.make_entry(
                    self._key,
                    seq=seq,
                    ts=ts,
                    actor=actor,
                    action=action,
                    payload=payload,
                    prev_hmac=prev_hmac,
                )
                self._conn.execute(
                    "INSERT INTO audit (seq, ts, actor, action, payload_digest, prev_hmac, hmac, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry["seq"],
                        entry["ts"],
                        entry["actor"],
                        entry["action"],
                        entry["payload_digest"],
                        entry["prev_hmac"],
                        entry["hmac"],
                        ledger.canonical(payload),
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return entry

    def entries(self) -> list[dict[str, Any]]:
        """All ledger entries (signed fields + hmac), ordered by seq."""
        rows = self._conn.execute(
            "SELECT seq, ts, actor, action, payload_digest, prev_hmac, hmac FROM audit ORDER BY seq"
        ).fetchall()
        return [dict(row) for row in rows]

    def export(self) -> list[dict[str, Any]]:
        """Full export including stored payloads, for an external verifier."""
        rows = self._conn.execute(
            "SELECT seq, ts, actor, action, payload_digest, prev_hmac, hmac, payload_json "
            "FROM audit ORDER BY seq"
        ).fetchall()
        return [dict(row) for row in rows]

    def verify(self) -> bool:
        """Verify chain integrity *and* that each stored payload matches its digest.

        Raises :class:`ledger.ChainError` on the first problem. The payload check
        catches a tamperer who edits ``payload_json`` (the human-readable detail)
        without touching the signed digest.
        """
        entries = self.export()
        ledger.verify_chain(self._key, entries)
        for entry in entries:
            recomputed = ledger.payload_digest(json.loads(entry["payload_json"]))
            if recomputed != entry["payload_digest"]:
                raise ledger.ChainError(entry["seq"], "stored payload does not match its digest")
        return True

    def close(self) -> None:
        self._conn.close()
