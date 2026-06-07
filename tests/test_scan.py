"""End-to-end scan route test with the CV layer faked.

The dlib-backed detection/encoding is replaced with deterministic stand-ins so we
can prove the *governance wiring* of the scan path without real face images:
reference uploads create consent records, the policy verdict is applied, and both
the enrollment and the scan land in the audit ledger.
"""

import io

import numpy as np

import app.main as main
from app.models import ConsentRecord
from app.recognition import Detection
from tests.conftest import login, register


def _fake_cv(monkeypatch, *, matched: bool):
    """Patch encode/scan/annotate so a scan resolves deterministically."""
    monkeypatch.setattr(main, "encode_single_face", lambda data, *a, **k: np.zeros(128))

    def fake_scan(data, known, tolerance=0.6, max_width=1024, **kwargs):
        idx = 0 if (matched and len(known) > 0) else None
        det = Detection(location=(0, 10, 10, 0), matched_index=idx, distance=0.3)
        return [det], np.zeros((10, 10, 3), dtype=np.uint8)

    monkeypatch.setattr(main, "scan_faces", fake_scan)
    monkeypatch.setattr(main, "annotate", lambda image, boxes: "")


def _img(name):
    return (io.BytesIO(b"not-a-real-image-but-cv-is-faked"), name)


def post_scan(client, *, status, mode):
    return client.post(
        "/scan",
        data={
            "consent_status": status,
            "mode": mode,
            "lawful_basis": "guardian declined release 2024-06",
            "reference_faces": _img("jane-doe.jpg"),
            "photos": _img("group-photo.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_scan_enrolls_record_and_flags_denylist_match(app, client, monkeypatch):
    _fake_cv(monkeypatch, matched=True)
    register(client)
    login(client)
    resp = post_scan(client, status="declined", mode="flag_matches")

    assert resp.status_code == 200
    assert b"need review" in resp.data  # a declined match is flagged

    with app.app_context():
        record = ConsentRecord.query.filter_by(label="jane-doe").first()
        assert record is not None
        assert record.consent_status == "declined"
        assert "declined release" in record.lawful_basis

    actions = [e["action"] for e in app.audit_store.entries()]
    assert "enroll_references" in actions
    assert "scan_batch" in actions
    assert app.audit_store.verify() is True


def test_scan_allowlist_passes_consented_match(app, client, monkeypatch):
    _fake_cv(monkeypatch, matched=True)
    register(client)
    login(client)
    resp = post_scan(client, status="consented", mode="flag_non_matches")

    assert resp.status_code == 200
    assert b"nothing flagged" in resp.data  # consented face on an allowlist run is fine


def test_scan_records_consent_status_in_audit_payload(app, client, monkeypatch):
    _fake_cv(monkeypatch, matched=True)
    register(client)
    login(client)
    post_scan(client, status="declined", mode="flag_matches")

    enroll = next(e for e in app.audit_store.export() if e["action"] == "enroll_references")
    assert '"consent_status":"declined"' in enroll["payload_json"]
    assert '"lawful_basis_present":true' in enroll["payload_json"]
