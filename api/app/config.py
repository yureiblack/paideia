"""Application settings, loaded from the environment and type-checked.

Purpose
-------
Centralized application configuration.

Loads environment variables into one typed and validated Settings object.
This avoids reading raw strings and repeating parsing, defaults, and validation
throughout the codebase.

Configuration is validated once at startup, so errors are caught early.
This module only handles configuration and does not depend on application logic.

It is the bottom of the dependency chain:
everything may import it, it imports nothing of ours.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# This file is api/app/config.py, so three levels up is the repository root,
# which is where .env lives. Derived from __file__ rather than the working
# directory, so it resolves correctly no matter where the server is started.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Every value the backend reads from the environment.

    Each attribute below is one setting, and its type annotation is the
    validation rule. Pydantic reads the matching environment variable, converts
    it to that type, and refuses to start if it cannot.
    """

    # env_file says where to read values from. extra="ignore" tolerates
    # variables in .env that belong to other tools, rather than rejecting them.
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # Matched to the DATABASE_URL variable, case-insensitively. Deliberately has
    # no default: a missing .env should stop the app at startup, not silently
    # connect somewhere unexpected.
    database_url: str

    # Browser origins allowed to call this API, as a comma-separated list.
    # Defaults to the local Next.js dev server, which is safe to assume: it
    # only ever permits a page running on this same machine.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        """cors_origins as a clean list, ignoring blanks and stray spaces."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


# The single shared instance, built once when this module is first imported.
# Every other module imports this object rather than constructing its own, so
# configuration is read and validated exactly once per process.
settings = Settings()
