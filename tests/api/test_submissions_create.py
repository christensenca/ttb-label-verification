"""Contract test for POST /api/submissions (T056, US2)."""

from __future__ import annotations

import io
import json
import uuid

from PIL import Image
from sqlalchemy import select

from app.db.models import Submission


def _make_jpeg(width: int = 4, height: int = 4) -> bytes:
    """Build a real, Pillow-decodable JPEG so the API's Pillow verify passes."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width: int = 4, height: int = 4) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(50, 100, 200)).save(buf, format="PNG")
    return buf.getvalue()


_TINY_JPEG = _make_jpeg()


def _expected_values_payload(**overrides) -> dict:
    base = {
        "brand": "User Brand",
        "class_type": "Whisky",
        "alcohol_content": 40.0,
        "net_contents": "750 mL",
        "producer_name": "User Distillery",
        "producer_address": "Somewhere, USA",
        "is_imported": False,
    }
    base.update(overrides)
    return base


def test_create_submission_happy_path_returns_201(client, db_session):
    response = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "loaded"
    new_id = uuid.UUID(body["id"])

    row = db_session.execute(
        select(Submission).where(Submission.id == new_id)
    ).scalars().first()
    assert row is not None
    assert row.is_fixture is False
    assert row.status == "loaded"
    assert row.image_key.startswith("sha256:")
    assert row.expected_values["brand"] == "User Brand"


def test_create_submission_missing_image_returns_400(client):
    response = client.post(
        "/api/submissions",
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    # FastAPI's missing-form-field response is 422 by default; our handler
    # promotes it to 400 with a human-readable detail.
    assert response.status_code == 400, response.text


def test_create_submission_non_json_expected_values_returns_400(client):
    response = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
        data={"expected_values": "this is not json"},
    )
    assert response.status_code == 400, response.text
    assert "json" in response.json()["detail"].lower()


def test_create_submission_is_imported_without_country_returns_400(client):
    payload = _expected_values_payload(is_imported=True, country_of_origin="")
    response = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
        data={"expected_values": json.dumps(payload)},
    )
    assert response.status_code == 400, response.text
    assert "country_of_origin" in response.json()["detail"]


def test_create_submission_oversize_image_returns_400(client):
    # 10 MB + 1 byte
    oversize = b"\xff" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/submissions",
        files={"image": ("big.jpg", io.BytesIO(oversize), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 400, response.text


def test_create_submission_non_image_bytes_returns_415(client):
    # Non-image bytes: we trust the file's magic, not the client-declared
    # content-type. Anything that doesn't match a supported image signature
    # comes back as 415 "not a recognized image".
    response = client.post(
        "/api/submissions",
        files={"image": ("label.txt", io.BytesIO(b"not an image"), "text/plain")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 415, response.text
    assert "not a recognized image" in response.json()["detail"]


def test_create_submission_mislabeled_content_type_is_accepted(client):
    # Real-world case: a PNG saved with a .jpg extension and uploaded as
    # image/jpeg. We trust the bytes and accept it.
    png_bytes = _make_png(width=10, height=10)
    response = client.post(
        "/api/submissions",
        files={"image": ("mislabeled.jpg", io.BytesIO(png_bytes), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 201, response.text


def test_create_submission_truncated_jpeg_returns_400(client):
    # Correct JPEG magic but truncated — Pillow verify() must reject it.
    truncated = _TINY_JPEG[:8]
    response = client.post(
        "/api/submissions",
        files={"image": ("truncated.jpg", io.BytesIO(truncated), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 400, response.text
    assert "invalid image" in response.json()["detail"]


def test_create_submission_pixel_bomb_returns_400(client):
    # An 8000x8000 PNG: under 10 MB on disk (PNG compresses solid colors well)
    # but exceeds the 40 MP pixel cap.
    huge = _make_png(width=8000, height=8000)
    assert len(huge) < 10 * 1024 * 1024, "fixture must stay under byte cap"
    response = client.post(
        "/api/submissions",
        files={"image": ("huge.png", io.BytesIO(huge), "image/png")},
        data={"expected_values": json.dumps(_expected_values_payload())},
    )
    assert response.status_code == 400, response.text
    assert "pixel limit" in response.json()["detail"]
