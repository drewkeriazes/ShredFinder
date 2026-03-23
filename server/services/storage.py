"""File storage abstraction.

Provides a local filesystem implementation that can be swapped to S3 later by
implementing the same interface.
"""

import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from server.config import settings


class StorageBackend(ABC):
    """Abstract storage interface."""

    @abstractmethod
    async def save_file(self, data: bytes, user_id: str, filename: str, subdir: str = "") -> str:
        """Save file bytes and return the relative storage path."""
        ...

    @abstractmethod
    async def save_upload(self, upload_file, user_id: str, filename: str) -> str:
        """Stream an UploadFile to disk and return the relative storage path."""
        ...

    @abstractmethod
    def get_file_path(self, relative_path: str) -> Path:
        """Resolve a relative storage path to an absolute filesystem path."""
        ...

    @abstractmethod
    async def delete_file(self, relative_path: str) -> None:
        """Delete a file by its relative storage path."""
        ...

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """Return a URL (or path) that the client can use to fetch this file."""
        ...


class LocalStorage(StorageBackend):
    """Store files on the local filesystem under DATA_DIR."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(self, data: bytes, user_id: str, filename: str, subdir: str = "") -> str:
        # Build unique path: {user_id}/{subdir}/{uuid}_{filename}
        unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
        rel_parts = [user_id]
        if subdir:
            rel_parts.append(subdir)
        rel_parts.append(unique_name)
        rel_path = "/".join(rel_parts)

        abs_path = self.base_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(abs_path, "wb") as f:
            await f.write(data)

        return rel_path

    async def save_upload(self, upload_file, user_id: str, filename: str) -> str:
        """Stream a Starlette/FastAPI UploadFile to disk in chunks."""
        unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
        rel_path = f"{user_id}/uploads/{unique_name}"

        abs_path = self.base_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(abs_path, "wb") as out:
            while chunk := await upload_file.read(1024 * 1024):  # 1 MB chunks
                await out.write(chunk)

        return rel_path

    def get_file_path(self, relative_path: str) -> Path:
        return self.base_dir / relative_path

    async def delete_file(self, relative_path: str) -> None:
        abs_path = self.base_dir / relative_path
        if abs_path.is_file():
            abs_path.unlink()
        elif abs_path.is_dir():
            shutil.rmtree(abs_path)

    def get_url(self, relative_path: str) -> str:
        return f"/static/{relative_path}"


# Module-level singleton
storage = LocalStorage()
