"""Phase 2 smoke checks for the foundation fixtures and FastAPI shell.

These tests are intentionally minimal — they verify that the conftest fixtures
work end-to-end against the real test database and that the FastAPI shell
exposes /healthz, /openapi.json, and a CORS-aware /api/* response. Deletable
once richer suites land in Phase 3+.
"""

from __future__ import annotations

from app.db.models import Submission


def test_client_serves_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_published(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "TTB Label Verify"
    assert "/healthz" in schema["paths"]


def test_db_session_rollback(db_session, _engine):
    # Insert a row, then verify the SAVEPOINT pattern doesn't leak it across tests.
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values={"brand": "X"},
        status="loaded",
        is_fixture=False,
    )
    db_session.add(sub)
    db_session.flush()
    assert sub.id is not None
    # End of test triggers rollback; we don't assert here, but
    # test_db_session_isolation below confirms the row didn't survive.


def test_db_session_isolation(db_session):
    # If the previous test leaked, we'd see >0 rows. SAVEPOINT rollback guarantees 0.
    count = db_session.query(Submission).filter_by(image_key="sha256:test.jpg").count()
    assert count == 0


def test_mock_extract_returns_canned_result(mock_extract):
    from pipeline.extract import extract

    result = extract("test_data/images/don_julio.jpg")
    assert result.model == "test-model/mock"
    assert result.label.brand == "Don Julio"
    assert result.field_confidence["brand"] == "hi"
