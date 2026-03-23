"""File storage abstraction.

Organizes files per-user, per-media:
  server/data/users/{user_id}/media/{media_id}/original.mp4
  server/data/users/{user_id}/media/{media_id}/proxy.mp4
  server/data/users/{user_id}/media/{media_id}/thumbnail.jpg
  server/data/users/{user_id}/renders/{job_id}.mp4

Can be swapped to S3 by implementing the same interface.
"""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from server.config import settings


class StorageBackend(ABC):
    """Abstract storage interface."""

    @abstractmethod
    async def save_upload(self, upload_file, user_id: str, media_id: str) -> str:
        """Stream an uploaded video to disk. Returns relative storage path."""
        ...

    @abstractmethod
    def get_file_path(self, relative_path: str) -> Path:
        """Resolve a relative storage path to an absolute filesystem path."""
        ...

    @abstractmethod
    def media_path(self, user_id: str, media_id: str, filename: str) -> tuple[Path, str]:
        """Get (absolute_path, relative_path) for a media asset."""
        ...

    @abstractmethod
    async def delete_media(self, user_id: str, media_id: str) -> None:
        """Delete all files for a media item."""
        ...


class LocalStorage(StorageBackend):
    """Store files on the local filesystem under DATA_DIR."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload_file, user_id: str, media_id: str) -> str:
        """Stream an uploaded file to disk as original.{ext}."""
        ext = "mp4"
        if upload_file.filename:
            parts = upload_file.filename.rsplit(".", 1)
            if len(parts) > 1:
                ext = parts[1].lower()

        abs_path, rel_path = self.media_path(user_id, media_id, f"original.{ext}")

        async with aiofiles.open(abs_path, "wb") as out:
            while chunk := await upload_file.read(1024 * 1024):  # 1 MB
                await out.write(chunk)

        return rel_path

    def get_file_path(self, relative_path: str) -> Path:
        return self.base_dir / relative_path

    def media_path(self, user_id: str, media_id: str, filename: str) -> tuple[Path, str]:
        """Return (absolute, relative) paths for a file within a media's folder."""
        rel = f"users/{user_id}/media/{media_id}/{filename}"
        abs_path = self.base_dir / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return abs_path, rel

    def render_path(self, user_id: str, job_id: str) -> tuple[Path, str]:
        """Return (absolute, relative) paths for a render output."""
        rel = f"users/{user_id}/renders/{job_id}.mp4"
        abs_path = self.base_dir / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return abs_path, rel

    async def delete_media(self, user_id: str, media_id: str) -> None:
        media_dir = self.base_dir / "users" / user_id / "media" / media_id
        if media_dir.is_dir():
            shutil.rmtree(media_dir)


# Module-level singleton
storage = LocalStorage()
