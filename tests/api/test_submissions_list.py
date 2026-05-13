"""Contract test for GET /api/submissions (T025, US1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Submission


def _insert(db_session, **kwargs) -> Submission:
    defaults = dict(
        image_key="sha256:test.jpg",
        expected_values={
            "brand": "Sample Brand",
            "class_type": "Whisky",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "Sample Distillery",
            "producer_address": "Anywhere, USA",
            "is_imported": False,
        },
        status="loaded",
        is_fixture=True,
    )
    defaults.update(kwargs)
    sub = Submission(**defaults)
    db_session.add(sub)
    db_session.flush()
    return sub


def test_list_returns_items_with_required_fields(client, db_session):
    base = datetime.now(UTC)
    for i in range(7):
        _insert(
            db_session,
            expected_values={
                **{
                    "brand": f"Brand{i}",
                    "class_type": "Whisky",
                    "alcohol_content": 40.0,
                    "net_contents": "750 mL",
                    "producer_name": "X",
                    "producer_address": "Y",
                    "is_imported": False,
                }
            },
            created_at=base - timedelta(seconds=i),
        )
    db_session.flush()

    response = client.get("/api/submissions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 7
    for item in body:
        assert {
            "id",
            "status",
            "brand",
            "is_fixture",
            "created_at",
            "thumbnail_url",
            "has_extraction_error",
        } <= set(item.keys())
        assert item["thumbnail_url"].startswith("/api/submissions/")


def test_list_ordering_is_created_at_desc(client, db_session):
    older = _insert(
        db_session,
        expected_values={
            "brand": "Older",
            "class_type": "Whisky",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "X",
            "producer_address": "Y",
            "is_imported": False,
        },
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    newer = _insert(
        db_session,
        expected_values={
            "brand": "Newer",
            "class_type": "Whisky",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "X",
            "producer_address": "Y",
            "is_imported": False,
        },
        created_at=datetime.now(UTC),
    )
    db_session.flush()

    body = client.get("/api/submissions").json()
    ids = [item["id"] for item in body]
    assert ids.index(str(newer.id)) < ids.index(str(older.id))
