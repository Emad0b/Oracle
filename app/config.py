from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".data"
TOKEN_PATH = DATA_DIR / "google_token.json"
OAUTH_STATE_PATH = DATA_DIR / "google_oauth_state.json"


def _env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if value else None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env_value(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str | None
    whisper_model: str
    google_client_id: str | None
    google_client_secret: str | None
    google_redirect_uri: str
    app_base_url: str
    show_hud: bool


def get_settings() -> Settings:
    return Settings(
        openai_api_key=_env_value("OPENAI_API_KEY"),
        openai_model=_env_value("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        openai_base_url=_env_value("OPENAI_BASE_URL"),
        whisper_model=_env_value("WHISPER_MODEL", "whisper-1") or "whisper-1",
        google_client_id=_env_value("GOOGLE_CLIENT_ID"),
        google_client_secret=_env_value("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=_env_value(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/google/callback",
        )
        or "http://127.0.0.1:8000/api/google/callback",
        app_base_url=_env_value("APP_BASE_URL", "http://127.0.0.1:8000")
        or "http://127.0.0.1:8000",
        show_hud=_env_bool("ORACLE_HUD", True),
    )
