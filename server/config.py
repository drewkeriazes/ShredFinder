"""Server configuration via pydantic-settings.

Loads from environment variables or a .env file in the project root.
"""

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Override any value via environment variable or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    APP_NAME: str = "ShredFinder"
    DEBUG: bool = False

    # --- Auth ---
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./server/data/shredfinder.db"

    # --- Storage directories ---
    DATA_DIR: Path = Path("server/data")
    UPLOAD_DIR: Path = Path("server/data/uploads")
    PROXY_DIR: Path = Path("server/data/proxies")
    THUMBNAIL_DIR: Path = Path("server/data/thumbnails")
    RENDER_DIR: Path = Path("server/data/renders")

    # --- FFmpeg ---
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"

    # --- Proxy settings ---
    PROXY_HEIGHT: int = 720
    PROXY_CRF: int = 23

    def ensure_dirs(self) -> None:
        """Create all storage directories if they don't exist."""
        for d in (self.DATA_DIR, self.UPLOAD_DIR, self.PROXY_DIR,
                  self.THUMBNAIL_DIR, self.RENDER_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
