"""Reads all settings from .env once, so the rest of the app never touches os.environ.

Secret values are never printed or logged: the Settings class has repr=False,
so even print(settings) only shows "<Settings object at ...>".
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The folder that holds app/, .env and certs/. Relative paths are resolved from here,
# so the server works no matter which folder it is started from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Values already set in the shell win over .env (load_dotenv does not override them).
load_dotenv(PROJECT_ROOT / ".env")


def _required(name: str) -> str:
    """Return a required setting, or stop with a message naming the missing variable."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing from .env (see .env.example).")
    return value


def _project_path(path_text: str) -> Path:
    """Turn a path from .env into an absolute path; relative paths start at the project root."""
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True, repr=False)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_seconds: int
    tidb_host: str
    tidb_port: int
    tidb_user: str
    tidb_password: str
    tidb_database: str
    tidb_ca_path: Path
    max_upload_mb: int
    upload_dir: Path


settings = Settings(
    gemini_api_key=_required("GEMINI_API_KEY"),
    gemini_model=_required("GEMINI_MODEL"),
    gemini_timeout_seconds=int(os.getenv("GEMINI_TIMEOUT_SECONDS", "180")),
    tidb_host=_required("TIDB_HOST"),
    tidb_port=int(_required("TIDB_PORT")),
    tidb_user=_required("TIDB_USER"),
    tidb_password=_required("TIDB_PASSWORD"),
    tidb_database=_required("TIDB_DATABASE"),
    tidb_ca_path=_project_path(_required("TIDB_CA_PATH")),
    max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "30")),
    upload_dir=PROJECT_ROOT / "uploads",
)
