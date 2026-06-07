"""Biometric recognition — strictly in memory, never to disk.

Two principles enforced here:

1. **No persistence.** Uploaded images are read as bytes and turned into face
   templates in memory. Neither the raw image nor the encoding is ever written
   to disk. The old version saved both into per-user folders; this one keeps
   them only as long as a single request is on the stack.

2. **Best match, not first match.** The previous code took the first encoding
   over the 0.6 tolerance — which mislabels when several enrolled faces are
   similar. Here we compute the full distance vector and pick the closest, and
   only accept it if it's within tolerance, returning the distance as a
   confidence signal.

The heavy ``face_recognition``/dlib import is confined to this module. The pure
matching math (:func:`face_distance`, :func:`best_match`) uses only numpy so it
can be unit-tested without loading any models.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

# Default dlib match threshold. Lower = stricter. 0.6 is the library default;
# exposed here so the operator can tune precision/recall for their photo set.
DEFAULT_TOLERANCE = 0.6

# Detection downscale cap. Larger preserves small/distant faces (group photos)
# at the cost of speed.
DEFAULT_MAX_WIDTH = 1024

# Pluggable detector + encoder knobs. Recognition is the commodity layer here, so
# the model is a swappable deployment choice behind this boundary — not something
# the governance layer or end users reach into.
#
#   detector "hog" — fast, CPU-friendly, misses small/angled faces (the group-
#                    photo weak spot). The sensible default.
#   detector "cnn" — dlib's MMOD CNN; much better recall, but ~10-100x slower on
#                    CPU. An operator/GPU choice, never a per-request one (DoS).
#   upsample       — times to upscale before detection; raises small-face recall
#                    at a speed/memory cost. 1 is plenty for most photos.
#   encoding "small" (5-point) vs "large" (68-point) landmark model; "large" is
#                    a bit more accurate at a small speed cost.
DETECTORS = {"hog", "cnn"}
ENCODING_MODELS = {"small", "large"}
DEFAULT_DETECTOR = "hog"
DEFAULT_UPSAMPLE = 1
DEFAULT_ENCODING_MODEL = "small"


def validate_recognition_config(detector: str, encoding_model: str, upsample: int) -> None:
    """Fail fast on a bad recognition config (called at app startup).

    Pure — no model loading — so it can validate config without importing dlib.
    """
    if detector not in DETECTORS:
        raise ValueError(f"detector must be one of {sorted(DETECTORS)}, got {detector!r}")
    if encoding_model not in ENCODING_MODELS:
        raise ValueError(f"encoding model must be one of {sorted(ENCODING_MODELS)}, got {encoding_model!r}")
    if not isinstance(upsample, int) or upsample < 0:
        raise ValueError(f"upsample must be a non-negative int, got {upsample!r}")


def face_distance(known: np.ndarray, encoding: np.ndarray) -> np.ndarray:
    """Euclidean distance from one encoding to each known encoding.

    Equivalent to ``face_recognition.face_distance`` but dependency-free, so the
    matching logic is testable with synthetic vectors.
    """
    if len(known) == 0:
        return np.empty(0)
    return np.linalg.norm(np.asarray(known) - np.asarray(encoding), axis=1)


def best_match(
    known: np.ndarray,
    encoding: np.ndarray,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[Optional[int], float]:
    """Index of the closest known encoding within ``tolerance``, and its distance.

    Returns ``(None, distance)`` when nothing is close enough (distance is the
    best distance seen, or ``inf`` if the registry is empty).
    """
    distances = face_distance(known, encoding)
    if distances.size == 0:
        return None, float("inf")
    idx = int(np.argmin(distances))
    best = float(distances[idx])
    return (idx, best) if best <= tolerance else (None, best)


def _to_rgb_array(image_bytes: bytes, max_width: int) -> np.ndarray:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if image.size[0] > max_width:
        ratio = max_width / float(image.size[0])
        image = image.resize((max_width, int(image.size[1] * ratio)), Image.LANCZOS)
    return np.array(image)


def encode_single_face(
    image_bytes: bytes,
    detector: str = DEFAULT_DETECTOR,
    upsample: int = DEFAULT_UPSAMPLE,
    encoding_model: str = DEFAULT_ENCODING_MODEL,
) -> Optional[np.ndarray]:
    """Encode the most prominent face in an enrollment image, in memory.

    Returns ``None`` if no face is found. Used when adding someone to the
    registry — we keep the encoding in memory only for the lifetime of the scan
    that uses it.
    """
    import face_recognition  # local import: keep dlib out of import-time cost

    array = _to_rgb_array(image_bytes, DEFAULT_MAX_WIDTH)
    locations = face_recognition.face_locations(
        array, number_of_times_to_upsample=upsample, model=detector
    )
    if not locations:
        return None
    # Pick the largest face (closest to camera) for the most reliable template.
    locations.sort(key=lambda b: (b[2] - b[0]) * (b[1] - b[3]), reverse=True)
    encodings = face_recognition.face_encodings(array, [locations[0]], model=encoding_model)
    return encodings[0] if encodings else None


@dataclass
class Detection:
    """One face found in a scanned photo and who (if anyone) it matched."""

    location: tuple[int, int, int, int]   # (top, right, bottom, left)
    matched_index: Optional[int]
    distance: float


def scan_faces(
    image_bytes: bytes,
    known_encodings: np.ndarray,
    tolerance: float = DEFAULT_TOLERANCE,
    max_width: int = DEFAULT_MAX_WIDTH,
    detector: str = DEFAULT_DETECTOR,
    upsample: int = DEFAULT_UPSAMPLE,
    encoding_model: str = DEFAULT_ENCODING_MODEL,
) -> tuple[list[Detection], np.ndarray]:
    """Detect and match every face in a photo, in memory.

    Returns the detections plus the (possibly downscaled) RGB array, so the
    caller can annotate for display without re-decoding. Nothing is written to
    disk.
    """
    import face_recognition

    array = _to_rgb_array(image_bytes, max_width)
    locations = face_recognition.face_locations(
        array, number_of_times_to_upsample=upsample, model=detector
    )
    encodings = face_recognition.face_encodings(array, locations, model=encoding_model)

    detections = []
    for location, encoding in zip(locations, encodings):
        idx, distance = best_match(known_encodings, encoding, tolerance)
        detections.append(Detection(location=location, matched_index=idx, distance=distance))
    return detections, array


# Box colors in BGR (OpenCV's order): flagged faces in red, cleared in green.
_FLAG_BGR = (38, 38, 220)
_OK_BGR = (74, 163, 22)


def annotate(image_rgb: np.ndarray, boxes: list[tuple[tuple[int, int, int, int], bool, str]]) -> str:
    """Draw labelled boxes on a scanned image and return a base64 JPEG.

    ``boxes`` is ``(location, flagged, label)`` per face. The annotated image is
    produced and base64-encoded in memory — it is never written to disk.
    """
    import cv2

    canvas = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    for (top, right, bottom, left), flagged, label in boxes:
        color = _FLAG_BGR if flagged else _OK_BGR
        cv2.rectangle(canvas, (left, top), (right, bottom), color, 2)
        cv2.putText(canvas, label, (left, max(top - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    ok, buffer = cv2.imencode(".jpg", canvas)
    if not ok:
        raise ValueError("failed to encode annotated image")
    return base64.b64encode(buffer.tobytes()).decode("ascii")
