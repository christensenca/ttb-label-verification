"""Contract test for POST /api/submissions/bulk."""

from __future__ import annotations

import io

from PIL import Image
from sqlalchemy import select

from app.db.models import Submission


def _jpeg(width: int = 4, height: int = 4, color=(120, 60, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="JPEG")
    return buf.getvalue()


_HEADER = (
    "filename,brand,class_type,alcohol_content,net_contents,"
    "producer_name,producer_address,is_imported,country_of_origin"
)


def _files(*pairs):
    """Build a list of ('images', (name, bytes, content_type)) tuples."""
    return [("images", (name, io.BytesIO(blob), ct)) for name, blob, ct in pairs]


def test_bulk_happy_path_creates_each_row(client, db_session):
    csv = (
        f"{_HEADER}\n"
        "label-a.jpg,Brand A,Whisky,40.0,750 mL,Producer A,City ST,false,\n"
        "label-b.jpg,Brand B,Gin,42.5,1 L,Producer B,Town ST,true,Scotland\n"
    )
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv")),
            *_files(("label-a.jpg", _jpeg(), "image/jpeg")),
            *_files(("label-b.jpg", _jpeg(color=(50, 200, 100)), "image/jpeg")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["created"]) == 2
    assert body["errors"] == []
    assert {c["status"] for c in body["created"]} == {"loaded"}

    rows = db_session.execute(select(Submission)).scalars().all()
    user_rows = [r for r in rows if not r.is_fixture]
    assert {r.expected_values["brand"] for r in user_rows} == {"Brand A", "Brand B"}


def test_bulk_accepts_valid_skips_invalid(client, db_session):
    csv = (
        f"{_HEADER}\n"
        "ok.jpg,Brand OK,Whisky,40.0,750 mL,Producer,City ST,false,\n"
        "bad-row.jpg,Brand,Whisky,not_a_number,750 mL,Producer,City ST,false,\n"
        "missing-img.jpg,Brand,Whisky,40.0,750 mL,Producer,City ST,false,\n"
    )
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv")),
            *_files(("ok.jpg", _jpeg(), "image/jpeg")),
            *_files(("bad-row.jpg", _jpeg(), "image/jpeg")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["created"]) == 1
    reasons = {(e["row"], e["filename"]): e["reason"] for e in body["errors"]}
    # Row 2: bad alcohol_content
    assert any("alcohol_content" in r for r in reasons.values())
    # Row 3: image not uploaded
    assert any("no uploaded image matches" in r for r in reasons.values())


def test_bulk_reports_orphan_images(client):
    csv = (
        f"{_HEADER}\n"
        "used.jpg,Brand,Whisky,40.0,750 mL,Producer,City ST,false,\n"
    )
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv")),
            *_files(("used.jpg", _jpeg(), "image/jpeg")),
            *_files(("orphan.jpg", _jpeg(), "image/jpeg")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["created"]) == 1
    orphan_errors = [e for e in body["errors"] if e["filename"] == "orphan.jpg"]
    assert len(orphan_errors) == 1
    assert "not referenced" in orphan_errors[0]["reason"]


def test_bulk_missing_csv_returns_400(client):
    response = client.post(
        "/api/submissions/bulk",
        files=_files(("a.jpg", _jpeg(), "image/jpeg")),
    )
    assert response.status_code == 400, response.text
    assert "csv" in response.json()["detail"].lower()


def test_bulk_missing_images_returns_400(client):
    csv = f"{_HEADER}\na.jpg,Brand,Whisky,40.0,750 mL,Producer,City ST,false,\n"
    response = client.post(
        "/api/submissions/bulk",
        files=[("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv"))],
    )
    assert response.status_code == 400, response.text
    assert "image" in response.json()["detail"].lower()


def test_bulk_csv_missing_columns_returns_400(client):
    bad_header = "filename,brand,alcohol_content\nlabel.jpg,Brand,40.0\n"
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("bad.csv", io.BytesIO(bad_header.encode()), "text/csv")),
            *_files(("label.jpg", _jpeg(), "image/jpeg")),
        ],
    )
    assert response.status_code == 400, response.text
    assert "missing required columns" in response.json()["detail"]


def test_bulk_duplicate_csv_filename_flagged(client):
    csv = (
        f"{_HEADER}\n"
        "same.jpg,Brand A,Whisky,40.0,750 mL,Producer,City ST,false,\n"
        "same.jpg,Brand B,Whisky,40.0,750 mL,Producer,City ST,false,\n"
    )
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv")),
            *_files(("same.jpg", _jpeg(), "image/jpeg")),
        ],
    )
    body = response.json()
    assert response.status_code == 200, response.text
    assert len(body["created"]) == 1
    dup_errors = [e for e in body["errors"] if "duplicate" in e["reason"]]
    assert len(dup_errors) == 1
    assert dup_errors[0]["filename"] == "same.jpg"


def test_bulk_invalid_imported_country_combo_flagged(client):
    csv = (
        f"{_HEADER}\n"
        "label.jpg,Brand,Whisky,40.0,750 mL,Producer,City ST,true,\n"
    )
    response = client.post(
        "/api/submissions/bulk",
        files=[
            ("csv", ("manifest.csv", io.BytesIO(csv.encode()), "text/csv")),
            *_files(("label.jpg", _jpeg(), "image/jpeg")),
        ],
    )
    body = response.json()
    assert response.status_code == 200, response.text
    assert body["created"] == []
    assert any("country_of_origin" in e["reason"] for e in body["errors"])
