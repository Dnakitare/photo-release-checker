"""Tests for the consent model and scan policy decisions."""

from app.governance.policy import (
    ConsentStatus,
    FaceDecision,
    Individual,
    ScanMode,
    decide_face,
    evaluate_photo,
)


def make_individual(status: ConsentStatus) -> Individual:
    return Individual(
        id="ind-1",
        label="Pat",
        consent_status=status,
        lawful_basis="test basis",
        enrolled_at=1000.0,
        retention_expiry=2000.0,
    )


# --- denylist (FLAG_MATCHES) -------------------------------------------------

def test_denylist_flags_declined_match():
    d = decide_face(make_individual(ConsentStatus.DECLINED), ScanMode.FLAG_MATCHES)
    assert d.flagged is True and d.matched_id == "ind-1"


def test_denylist_does_not_flag_consented_match():
    d = decide_face(make_individual(ConsentStatus.CONSENTED), ScanMode.FLAG_MATCHES)
    assert d.flagged is False


def test_denylist_ignores_non_match():
    d = decide_face(None, ScanMode.FLAG_MATCHES)
    assert d.flagged is False and d.matched_id is None


# --- allowlist (FLAG_NON_MATCHES) --------------------------------------------

def test_allowlist_flags_unrecognized_face():
    d = decide_face(None, ScanMode.FLAG_NON_MATCHES)
    assert d.flagged is True
    assert "no consent" in d.reason


def test_allowlist_passes_consented_match():
    d = decide_face(make_individual(ConsentStatus.CONSENTED), ScanMode.FLAG_NON_MATCHES)
    assert d.flagged is False


def test_allowlist_flags_enrolled_but_not_consented():
    d = decide_face(make_individual(ConsentStatus.UNKNOWN), ScanMode.FLAG_NON_MATCHES)
    assert d.flagged is True


# --- aggregation -------------------------------------------------------------

def test_evaluate_photo_counts_flags_and_review_flag():
    decisions = [
        FaceDecision("a", True, "x"),
        FaceDecision("b", False, "y"),
        FaceDecision(None, True, "z"),
    ]
    verdict = evaluate_photo(decisions)
    assert verdict.faces == 3
    assert verdict.flagged_faces == 2
    assert verdict.needs_review is True


def test_evaluate_clean_photo_needs_no_review():
    verdict = evaluate_photo([FaceDecision("a", False, "ok")])
    assert verdict.needs_review is False
