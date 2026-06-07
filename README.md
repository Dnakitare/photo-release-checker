# Photo Release Checker

A reference architecture for **privacy-by-design biometric processing**.

The face-matching here is commodity — about sixty lines wrapping
[`face_recognition`](https://github.com/ageitgey/face_recognition). The point of
this project is everything *around* it: how you run facial recognition on a batch
of photos without retaining biometric data, while keeping a tamper-evident record
of every decision. It started as a tool to help a summer-camp social-media
director flag photos of people who hadn't signed a release, and was rebuilt around
the governance question that use case actually raises: *how do you do this
responsibly, and prove that you did?*

## The four guarantees

| Guarantee | How it's enforced |
|---|---|
| **Biometric templates are never persisted** | Reference faces and scanned photos are read into memory, encoded, matched, annotated, and dropped when the request ends. No encoding or image is written to disk — and there is no database column for one. |
| **Every privacy-relevant action is tamper-evident** | Enroll, scan, and purge events are links in an HMAC-chained, append-only ledger ([`app/governance/ledger.py`](app/governance/ledger.py)). Each entry commits to the previous one; altering, inserting, reordering, or deleting any entry breaks verification from that point on. |
| **Consent is explicit and policy-driven** | Each enrolled individual carries a `consent_status` and a `lawful_basis`. The operator chooses whether a scan flags *matches* (a denylist) or *non-matches* (an allowlist — anyone not provably consented is surfaced for review). |
| **Data minimization is scheduled, not aspirational** | Consent metadata carries a retention window (90 days by default). Expired records are purged, and the purge is itself written to the ledger. |

## Architecture

```
app/
  __init__.py          application factory: extensions, config, audit store
  auth.py              registration/login (CSRF-protected, audited)
  main.py              enroll + scan (in memory), registry, audit-trail screen
  models.py            User + ConsentRecord  (no biometric columns, by design)
  recognition.py       in-memory encoding + best-match scoring; dlib isolated here
  governance/
    ledger.py          pure HMAC-chain core (no Flask, no DB, no clock)
    store.py           append-only SQLite ledger, separate from the app DB
    policy.py          consent model + deny/allow-list decisions
    retention.py       TTL expiry decisions
tools/
  verify_audit.py      standalone verifier — confirm the log independently
```

Two design choices worth calling out:

- **The audit ledger lives in its own SQLite database**, separate from the
  application's. The app's tables are mutable; the ledger's only verb is
  `INSERT`. Appends take SQLite's write lock (`BEGIN IMMEDIATE`, WAL mode) so
  sequence numbers stay correct even across multiple gunicorn workers.
- **The ledger core is pure.** It serializes deterministically and computes/
  verifies HMACs over plain dicts, with the caller supplying the sequence number
  and clock. The exact same code verifies inside the app, inside the test suite,
  and inside the standalone `verify_audit.py`.

## Run it

```bash
cp .example.env .env          # set SECRET_KEY and AUDIT_KEY
docker compose up --build     # http://localhost:5001
```

Or locally:

```bash
pip install -r requirements.txt
export SECRET_KEY=... AUDIT_KEY=...
flask --app wsgi run          # dev
gunicorn wsgi:app             # prod
```

`AUDIT_KEY` must stay stable across restarts — it signs the ledger, so a changed
key invalidates past entries.

## Recognition model (tunable)

Recognition is the commodity layer here, so the detector sits behind a swappable
boundary and is a **deployment-level** choice — never per-request, since the CNN
path is far slower and would otherwise be a DoS vector.

| Env var | Default | Notes |
|---|---|---|
| `FACE_DETECTOR` | `hog` | `hog` (fast, CPU) or `cnn` (better recall, GPU-friendly, slow on CPU) |
| `FACE_UPSAMPLE` | `1` | times to upscale before detection; higher finds smaller faces, slower |
| `FACE_ENCODING_MODEL` | `small` | `small` (5-point) or `large` (68-point landmarks) |

Measured on a 9-person group photo (1024px, CPU), enrolling one reference face:

| Detector | Faces found | Reference matched | Time |
|---|---|---|---|
| `hog` | 6 | ✓ (0.570) | 0.2s |
| `cnn` | 8 | ✓ (0.558) | 2.5s |

CNN recovers the small/angled faces HOG misses, at ~12× the latency — pick per
deployment. (Notably, bumping `FACE_UPSAMPLE` did *not* help on this image and
shifted the reference crop enough to break the match; more preprocessing isn't
free.) Swapping in a different detector entirely (RetinaFace, SCRFD) is a matter
of replacing the calls in `app/recognition.py` — the governance layer is
unaffected.

## Verify the audit log yourself

The "prove it" tool checks an exported ledger with nothing but the signing key:

```bash
python tools/verify_audit.py --db instance/audit.db --key "$AUDIT_KEY"
# OK: 3 entries verified — chain intact.
```

Tamper with any row via raw SQL and it fails, pinpointing the broken link:

```
FAIL: audit chain broken at seq=0: stored payload does not match its digest
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q        # 57 tests
```

The suite runs without the dlib/OpenCV stack — the CV layer is imported lazily
and faked in tests — so CI stays fast. The matching math is covered with
synthetic encodings; the live recognition path is verified manually.

## What this is, and isn't

This is a **reference architecture and portfolio piece**, not a turnkey product.
The recognition accuracy is whatever `face_recognition` gives you; the value is
the governance scaffolding around it.

A note on the problem domain: running facial recognition on people — especially
minors, especially those who *declined* a release — sits on contested legal
ground (e.g. Illinois BIPA, Texas CUPA/CUBI). The design here is the mitigation,
not a green light: templates are never retained, consent and lawful basis are
first-class, retention is enforced, and every action is independently auditable.
Anyone deploying this should get their own legal review first.

## License

Apache 2.0 — see [LICENSE](LICENSE).
