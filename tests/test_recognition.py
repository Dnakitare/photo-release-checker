"""Tests for the pure matching math in the recognition layer.

These use synthetic encodings so they run without loading dlib/face_recognition
models. The detection/encoding functions that need real models aren't exercised
here — they're covered by manual end-to-end verification.
"""

import numpy as np

from app.recognition import best_match, face_distance


def test_face_distance_empty_registry():
    assert face_distance(np.empty((0, 3)), np.array([1.0, 2.0, 3.0])).size == 0


def test_face_distance_computes_euclidean():
    known = np.array([[0.0, 0.0], [3.0, 4.0]])
    d = face_distance(known, np.array([0.0, 0.0]))
    assert np.allclose(d, [0.0, 5.0])


def test_best_match_picks_closest_within_tolerance():
    known = np.array([[0.0, 0.0], [0.1, 0.0], [1.0, 1.0]])
    idx, dist = best_match(known, np.array([0.09, 0.0]), tolerance=0.6)
    assert idx == 1  # closest, not merely first-over-threshold
    assert dist < 0.6


def test_best_match_returns_none_when_nothing_within_tolerance():
    known = np.array([[5.0, 5.0], [6.0, 6.0]])
    idx, dist = best_match(known, np.array([0.0, 0.0]), tolerance=0.6)
    assert idx is None
    assert dist > 0.6  # reports the best distance seen, for diagnostics


def test_best_match_empty_registry_is_no_match():
    idx, dist = best_match(np.empty((0, 128)), np.zeros(128))
    assert idx is None and dist == float("inf")
