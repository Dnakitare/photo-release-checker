"""Tests for recognition config validation (pure, no dlib)."""

import pytest

from app import create_app
from app.recognition import validate_recognition_config


def test_valid_configs_pass():
    validate_recognition_config("hog", "small", 1)
    validate_recognition_config("cnn", "large", 0)


@pytest.mark.parametrize("detector", ["HOG", "yolo", "", None])
def test_bad_detector_rejected(detector):
    with pytest.raises(ValueError, match="detector"):
        validate_recognition_config(detector, "small", 1)


def test_bad_encoding_model_rejected():
    with pytest.raises(ValueError, match="encoding model"):
        validate_recognition_config("hog", "huge", 1)


@pytest.mark.parametrize("upsample", [-1, 1.5, "2"])
def test_bad_upsample_rejected(upsample):
    with pytest.raises(ValueError, match="upsample"):
        validate_recognition_config("hog", "small", upsample)


def test_app_factory_rejects_bad_detector(tmp_path):
    with pytest.raises(ValueError, match="detector"):
        create_app({
            "TESTING": True,
            "FACE_DETECTOR": "nonsense",
            "AUDIT_DB_PATH": str(tmp_path / "audit.db"),
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'app.db'}",
        })


def test_app_factory_defaults_to_hog(app):
    assert app.config["FACE_DETECTOR"] == "hog"
    assert app.config["FACE_ENCODING_MODEL"] == "small"
