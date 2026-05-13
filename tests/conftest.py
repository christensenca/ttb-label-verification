"""Shared pytest fixtures for the compare/normalize/bench-replay AND API/service suites.

The API/service fixtures (`db_session`, `client`, `mock_extract`) run against a
dedicated test database, derived from `DATABASE_URL` by swapping the database
name to `ttb_verify_test` (or `TEST_DATABASE_URL` if explicitly set). Each test
runs in a SAVEPOINT-based rollback so no test persists state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "extractions.json"
EXPECTED_DIR = REPO / "test_data" / "expected"


@pytest.fixture(scope="session")
def extractions() -> dict:
    """Cached extraction outputs, shape::

    { bottle: { model: { "label": {...}, "latency_ms": ..., "error": ... } } }
    """
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="session")
def expected_for():
    """Returns a callable: bottle -> expected-values dict (the inner
    "expected" object from test_data/expected/<bottle>.json)."""

    cache: dict[str, dict] = {}

    def _get(bottle: str) -> dict:
        if bottle not in cache:
            cache[bottle] = json.loads((EXPECTED_DIR / f"{bottle}.json").read_text())["expected"]
        return cache[bottle]

    return _get


# --- API / service fixtures ------------------------------------------------


def _test_database_url() -> str:
    """Derive the test-database URL from settings, swapping the DB name."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    # Import lazily so the cheap fixtures above don't pull pydantic-settings.
    from app.config import get_settings

    parsed = urlparse(get_settings().database_url)
    # parsed.path is `/<dbname>` — swap to the test DB
    new_path = "/ttb_verify_test"
    return urlunparse(parsed._replace(path=new_path))


def _ensure_test_db_exists(url: str) -> None:
    """Create the test database if it doesn't already exist."""
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
        ).first()
        if exists is None:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def _engine() -> Iterator[Engine]:
    """Session-scoped test engine: ensures the DB exists, runs migrations once."""
    url = _test_database_url()
    _ensure_test_db_exists(url)

    # Run Alembic against the test DB.
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "app" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(_engine: Engine) -> Iterator[Session]:
    """Transactional rollback per test: each test gets a SAVEPOINT-isolated Session."""
    connection = _engine.connect()
    transaction = connection.begin()
    SessionFactory = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
        join_transaction_mode="create_savepoint",
    )
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session):
    """FastAPI TestClient with `get_db` overridden to share the test's session."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        # Skip lifespan (rescue + seed touches the real engine) for unit/contract tests.
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def mock_extract(monkeypatch: pytest.MonkeyPatch, extractions: dict):
    """Monkeypatch `pipeline.extract.extract` to return a canned ExtractionResult.

    Default behavior: returns a fixed result based on the don_julio cached
    extraction. Tests can pass a custom `ExtractionResult` (or factory) via the
    helper returned from this fixture::

        mock_extract.set(lambda image_path: my_custom_result)
    """
    from pipeline.extract import ExtractedLabel, ExtractionResult

    don_julio = extractions["don_julio"]["openai/gpt-4o-mini"]
    label_dict = {
        k: v
        for k, v in don_julio["label"].items()
        if k in ExtractedLabel.model_fields
    }
    default_result = ExtractionResult(
        label=ExtractedLabel(**label_dict),
        latency_ms=float(don_julio.get("latency_ms") or 1234.0),
        input_tokens=int(don_julio.get("in_tok") or 100),
        output_tokens=int(don_julio.get("out_tok") or 50),
        model="test-model/mock",
        field_confidence={
            "brand": "hi",
            "class_type": "hi",
            "alcohol_content": "hi",
            "net_contents": "hi",
            "producer_name": "hi",
            "producer_address": "hi",
            "country_of_origin": "hi",
            "government_warning_text": "hi",
        },
    )

    state: dict[str, object] = {"impl": lambda _path, **_kw: default_result}

    def _fake_extract(image_path, **kwargs):  # type: ignore[no-untyped-def]
        impl = state["impl"]
        result = impl(image_path, **kwargs) if callable(impl) else impl
        if isinstance(result, ExtractionResult):
            return result
        raise TypeError("mock_extract impl must return an ExtractionResult")

    import pipeline.extract as extract_module

    monkeypatch.setattr(extract_module, "extract", _fake_extract)

    class _Handle:
        default = default_result

        def set(self, impl):  # type: ignore[no-untyped-def]
            state["impl"] = impl

        def set_result(self, result: ExtractionResult) -> None:
            state["impl"] = lambda _p, **_kw: result

        def with_overrides(self, **overrides) -> ExtractionResult:  # type: ignore[no-untyped-def]
            return replace(default_result, **overrides)

    return _Handle()
