"""Image storage interface and the filesystem implementation.

Submissions store an `image_key` (e.g. `sha256:<hex>.jpg`), never an absolute
path. Swapping in an Azure Blob backend is a drop-in: implement `ImageStore`
and wire it up in the FastAPI dependency layer.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Protocol

_EXT_FOR_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _key_for(content: bytes, content_type: str) -> str:
    digest = hashlib.sha256(content).hexdigest()
    ext = _EXT_FOR_CONTENT_TYPE.get(content_type.lower())
    if ext is None:
        raise ValueError(f"Unsupported image content_type: {content_type!r}")
    return f"sha256:{digest}.{ext}"


class ImageStore(Protocol):
    """Content-addressed image store. Keys are opaque strings; never paths."""

    def put(self, content: bytes, content_type: str) -> str:
        """Persist bytes and return the storage key."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open the stored image for reading. Caller must close."""
        ...

    def delete(self, key: str) -> None:
        """Best-effort delete; no error if the key does not exist."""
        ...


class FilesystemImageStore:
    """`ImageStore` backed by a local directory (`IMAGE_STORAGE_DIR`)."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # Keys look like "sha256:<hex>.<ext>". `:` is awkward on some filesystems
        # but is fine on POSIX and the Railway volume — keep the key literal so
        # an Azure Blob backend can use the same string.
        return self._root / key

    def put(self, content: bytes, content_type: str) -> str:
        key = _key_for(content, content_type)
        target = self._path_for(key)
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(content)
            tmp.replace(target)
        return key

    def open(self, key: str) -> BinaryIO:
        return self._path_for(key).open("rb")

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)
