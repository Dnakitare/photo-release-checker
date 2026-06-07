"""Consent model and scan policy.

This is the conceptual heart of the privacy-by-design reframe. An enrolled
individual is not just "a known face" — it's a record with an explicit consent
status and the lawful basis under which their biometric template is held. The
operator configures whether a scan flags *matches* (a denylist: people who must
not appear) or *non-matches* (an allowlist: anyone who hasn't consented is
surfaced for manual review).

Everything here is pure data + decisions — no biometrics, no I/O — so the policy
can be unit-tested exhaustively and reasoned about independently of the CV layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConsentStatus(str, Enum):
    """Where an enrolled individual stands on appearing in published photos."""

    CONSENTED = "consented"      # signed a release; appearance is permitted
    DECLINED = "declined"        # explicitly declined a release
    UNKNOWN = "unknown"          # enrolled but status not yet established


class ScanMode(str, Enum):
    """What the operator wants a scan to surface."""

    FLAG_MATCHES = "flag_matches"          # denylist: flag photos containing enrolled people
    FLAG_NON_MATCHES = "flag_non_matches"  # allowlist: flag faces NOT on the consented list


@dataclass(frozen=True)
class Individual:
    """An enrolled person. The face template itself is NOT stored here — only
    the governance metadata. Templates live in memory for the duration of a scan
    and are never persisted (see :mod:`app.governance` and the recognition layer).
    """

    id: str
    label: str                       # operator-facing name or pseudonym
    consent_status: ConsentStatus
    lawful_basis: str                # e.g. "guardian declined release form 2024-06"
    enrolled_at: float               # epoch seconds
    retention_expiry: float          # epoch seconds; template purged after this


@dataclass(frozen=True)
class FaceDecision:
    """The governance verdict for a single detected face in a scanned photo."""

    matched_id: Optional[str]        # enrolled individual id, or None if no match
    flagged: bool
    reason: str


def decide_face(
    matched: Optional[Individual],
    mode: ScanMode,
) -> FaceDecision:
    """Apply the active scan policy to one detected face.

    ``matched`` is the enrolled individual this face resolved to, or ``None`` if
    it matched nobody in the registry.
    """
    if mode is ScanMode.FLAG_MATCHES:
        if matched is None:
            return FaceDecision(None, False, "no enrolled match")
        if matched.consent_status is ConsentStatus.CONSENTED:
            # On a denylist run, a consented person is explicitly allowed.
            return FaceDecision(matched.id, False, "matched but consent on file")
        return FaceDecision(
            matched.id, True, f"matched enrolled individual ({matched.consent_status.value})"
        )

    # FLAG_NON_MATCHES — allowlist: anyone not provably consented is surfaced.
    if matched is None:
        return FaceDecision(None, True, "unrecognized face — no consent on file")
    if matched.consent_status is ConsentStatus.CONSENTED:
        return FaceDecision(matched.id, False, "consent on file")
    return FaceDecision(
        matched.id, True, f"enrolled but not consented ({matched.consent_status.value})"
    )


@dataclass(frozen=True)
class PhotoVerdict:
    """Aggregate result for one scanned photo."""

    faces: int
    flagged_faces: int
    decisions: list[FaceDecision]

    @property
    def needs_review(self) -> bool:
        return self.flagged_faces > 0


def evaluate_photo(decisions: list[FaceDecision]) -> PhotoVerdict:
    """Roll per-face decisions up into a single photo verdict."""
    flagged = sum(1 for d in decisions if d.flagged)
    return PhotoVerdict(faces=len(decisions), flagged_faces=flagged, decisions=decisions)
