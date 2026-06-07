#!/usr/bin/env python3
"""Standalone audit-ledger verifier.

Independently checks an exported audit database with nothing but the signing key
and the pure ledger core — no Flask, no app context, no web server. This is the
"prove it" tool: hand someone the audit DB and the key and they can confirm for
themselves that the log was not altered, inserted into, reordered, or truncated.

    python tools/verify_audit.py --db instance/audit.db --key "$AUDIT_KEY"
    AUDIT_KEY=... python tools/verify_audit.py --db instance/audit.db

Exit code 0 = chain intact, 1 = verification failed, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

# Make the pure ledger core importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.governance import ledger  # noqa: E402


def load_entries(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT seq, ts, actor, action, payload_digest, prev_hmac, hmac, payload_json "
            "FROM audit ORDER BY seq"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def verify(db_path: str, key: bytes) -> int:
    entries = load_entries(db_path)
    try:
        ledger.verify_chain(key, entries)
        # Also confirm each stored payload still matches its committed digest.
        for entry in entries:
            recomputed = ledger.payload_digest(json.loads(entry["payload_json"]))
            if recomputed != entry["payload_digest"]:
                raise ledger.ChainError(entry["seq"], "stored payload does not match its digest")
    except ledger.ChainError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} verified — chain intact.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Photo Release Checker audit ledger.")
    parser.add_argument("--db", required=True, help="path to the audit SQLite database")
    parser.add_argument("--key", default=os.getenv("AUDIT_KEY"),
                        help="signing key (defaults to the AUDIT_KEY env var)")
    args = parser.parse_args()

    if not args.key:
        print("error: signing key required (pass --key or set AUDIT_KEY)", file=sys.stderr)
        return 2
    if not os.path.exists(args.db):
        print(f"error: no such database: {args.db}", file=sys.stderr)
        return 2
    return verify(args.db, args.key.encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
