"""Idempotent fixture seeder.

On first boot, inserts one submission per file in `test_data/expected/*.json`,
storing the matching `test_data/images/<bottle>.<ext>` via the configured
`ImageStore`. Status `loaded`, `is_fixture=True`. Skips entirely if any
`is_fixture=True` row already exists.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Submission
from app.db.session import SessionLocal
from app.services.storage import FilesystemImageStore, ImageStore

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DIR = REPO_ROOT / "test_data" / "expected"
IMAGES_DIR = REPO_ROOT / "test_data" / "images"


def _content_type_for(image_path: Path) -> str:
    guess, _ = mimetypes.guess_type(image_path.name)
    if guess:
        return guess
    suffix = image_path.suffix.lower().lstrip(".")
    return f"image/{'jpeg' if suffix == 'jpg' else suffix}"


def run_seed(image_store: ImageStore | None = None) -> int:
    """Insert fixture rows + copy images into storage. Returns rows inserted.

    Idempotent — returns 0 (and writes nothing) if any fixture rows already exist.
    """
    settings = get_settings()
    if image_store is None:
        image_store = FilesystemImageStore(settings.image_storage_dir)

    inserted = 0
    with SessionLocal() as session:
        existing = session.scalar(
            select(Submission.id).where(Submission.is_fixture.is_(True)).limit(1)
        )
        if existing is not None:
            logger.info("seed: fixtures already present, skipping")
            return 0

        if not EXPECTED_DIR.exists():
            logger.warning("seed: %s does not exist; nothing to seed", EXPECTED_DIR)
            return 0

        for expected_file in sorted(EXPECTED_DIR.glob("*.json")):
            bottle = expected_file.stem
            doc = json.loads(expected_file.read_text())
            image_name = doc.get("image") or f"{bottle}.jpg"
            image_path = IMAGES_DIR / image_name
            if not image_path.exists():
                logger.warning("seed: image %s not found, skipping %s", image_path, bottle)
                continue

            content = image_path.read_bytes()
            key = image_store.put(content, _content_type_for(image_path))
            session.add(
                Submission(
                    image_key=key,
                    expected_values=doc["expected"],
                    status="loaded",
                    is_fixture=True,
                )
            )
            inserted += 1

        session.commit()

    logger.info("seed: inserted %d fixture submissions", inserted)
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    count = run_seed()
    print(f"seeded: {count}")
