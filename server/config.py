"""Server configuration via pydantic-settings.

Loads from environment variables or a .env file in the project root.
"""

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
    # Fixed default for dev — override via SECRET_KEY env var in production
    SECRET_KEY: str = "shredfinder-dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./server/data/shredfinder.db"

    # --- Storage ---
    # All user files live under DATA_DIR/users/{user_id}/...
    DATA_DIR: Path = Path("server/data")

    # --- FFmpeg ---
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"

    # --- Proxy settings ---
    PROXY_HEIGHT: int = 720
    PROXY_CRF: int = 23

    def user_media_dir(self, user_id: str, media_id: str) -> Path:
        """Get the directory for a specific media file's assets."""
        d = self.DATA_DIR / "users" / user_id / "media" / media_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def user_renders_dir(self, user_id: str) -> Path:
        """Get the directory for a user's rendered exports."""
        d = self.DATA_DIR / "users" / user_id / "renders"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_dirs(self) -> None:
        """Create base storage directory."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
