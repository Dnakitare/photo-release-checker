"""Core application routes: enroll + scan, consent registry, and the audit trail.

The scan path is the privacy-critical one. Reference faces and photos are read
into memory, encoded, matched, annotated, and then dropped when the request
ends. Nothing biometric is written to disk. The persistent side effects are
limited to (a) consent *metadata* in the registry and (b) append-only entries in
the audit ledger.
"""

from __future__ import annotations

import os
import time

import numpy as np
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.governance import ledger, retention
from app.governance.policy import (
    ConsentStatus,
    ScanMode,
    decide_face,
    evaluate_photo,
)
from app.models import ConsentRecord
from app.recognition import annotate, encode_single_face, scan_faces

main_bp = Blueprint("main", __name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png"}


def _is_image(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXT


@main_bp.route("/")
@login_required
def index():
    records = ConsentRecord.query.filter_by(owner_id=current_user.id).all()
    return render_template(
        "index.html",
        records=records,
        modes=list(ScanMode),
        statuses=list(ConsentStatus),
    )


@main_bp.route("/scan", methods=["POST"])
@login_required
def scan():
    try:
        mode = ScanMode(request.form.get("mode", ScanMode.FLAG_MATCHES.value))
        status = ConsentStatus(request.form.get("consent_status", ConsentStatus.DECLINED.value))
    except ValueError:
        flash("Invalid scan options.", "danger")
        return redirect(url_for("main.index"))

    basis = (request.form.get("lawful_basis") or "").strip()
    tolerance = current_app.config["FACE_TOLERANCE"]
    retention_seconds = current_app.config["RETENTION_SECONDS"]
    audit = current_app.audit_store
    now = time.time()

    # --- 1. Build the in-memory registry from reference uploads -----------------
    known_encodings: list[np.ndarray] = []
    known_individuals = []  # parallel to known_encodings
    enrolled_labels: list[str] = []
    for file in request.files.getlist("reference_faces"):
        if not file.filename or not _is_image(file.filename):
            continue
        label = os.path.splitext(secure_filename(file.filename))[0] or "unnamed"
        encoding = encode_single_face(file.read())  # in memory only
        if encoding is None:
            flash(f"No face detected in reference '{label}' — skipped.", "warning")
            continue
        record = ConsentRecord.query.filter_by(owner_id=current_user.id, label=label).first()
        if record is None:
            record = ConsentRecord.make(current_user.id, label, status, basis, now, retention_seconds)
            db.session.add(record)
            db.session.flush()  # assign id for to_individual()
        else:  # re-enrolling refreshes the consent metadata
            record.consent_status = status.value
            if basis:
                record.lawful_basis = basis
        known_encodings.append(encoding)
        known_individuals.append(record.to_individual())
        enrolled_labels.append(label)
    db.session.commit()

    if enrolled_labels:
        audit.append(
            actor=current_user.username,
            action="enroll_references",
            payload={
                "labels": enrolled_labels,
                "consent_status": status.value,
                "lawful_basis_present": bool(basis),
                "count": len(enrolled_labels),
            },
        )

    # --- 2. Scan photos in memory ----------------------------------------------
    known_arr = np.array(known_encodings) if known_encodings else np.empty((0, 128))
    results = []
    total_faces = 0
    total_flagged = 0
    for file in request.files.getlist("photos"):
        if not file.filename or not _is_image(file.filename):
            continue
        filename = secure_filename(file.filename)
        try:
            detections, image_arr = scan_faces(file.read(), known_arr, tolerance)
        except Exception as exc:  # one bad photo must not abort the batch
            current_app.logger.error("scan failed for %s: %s", filename, exc)
            results.append({"file": filename, "error": "could not process image"})
            continue

        boxes = []
        decisions = []
        for det in detections:
            matched = known_individuals[det.matched_index] if det.matched_index is not None else None
            decision = decide_face(matched, mode)
            decisions.append(decision)
            tag = matched.label if matched else "unknown"
            caption = f"{'FLAG' if decision.flagged else 'ok'} {tag} {det.distance:.2f}"
            boxes.append((det.location, decision.flagged, caption))

        verdict = evaluate_photo(decisions)
        total_faces += verdict.faces
        total_flagged += verdict.flagged_faces
        results.append({
            "file": filename,
            "faces": verdict.faces,
            "flagged": verdict.flagged_faces,
            "needs_review": verdict.needs_review,
            "image": annotate(image_arr, boxes),
            "decisions": decisions,
        })

    audit.append(
        actor=current_user.username,
        action="scan_batch",
        payload={
            "mode": mode.value,
            "photos": len(results),
            "faces": total_faces,
            "flagged": total_flagged,
        },
    )
    # Biometric material (known_encodings, image arrays) goes out of scope here.
    return render_template("result.html", results=results, mode=mode,
                           total_flagged=total_flagged)


@main_bp.route("/registry")
@login_required
def registry():
    records = (
        ConsentRecord.query.filter_by(owner_id=current_user.id)
        .order_by(ConsentRecord.label)
        .all()
    )
    return render_template("registry.html", records=records, now=time.time())


@main_bp.route("/registry/purge", methods=["POST"])
@login_required
def purge():
    now = time.time()
    records = ConsentRecord.query.filter_by(owner_id=current_user.id).all()
    expired = [r for r in records if retention.is_expired(r.to_individual(), now)]
    for record in expired:
        db.session.delete(record)
    db.session.commit()
    current_app.audit_store.append(
        actor=current_user.username,
        action="purge_expired",
        payload={"removed": len(expired)},
    )
    flash(f"Purged {len(expired)} expired consent record(s).", "success")
    return redirect(url_for("main.registry"))


@main_bp.route("/audit")
@login_required
def audit_trail():
    store = current_app.audit_store
    entries = store.export()
    try:
        store.verify()
        verified, error = True, None
    except ledger.ChainError as exc:
        verified, error = False, str(exc)
    return render_template("audit.html", entries=entries, verified=verified, error=error)
