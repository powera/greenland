"""Configuration for data sources (storage backends, cache, LLM)."""

import os
from enum import Enum
from typing import Optional

import constants


class BackendType(Enum):
    """Supported storage backend types."""

    SQLITE = "sqlite"
    JSONL = "jsonl"


class DataSourceConfig:
    """Configuration for data sources: storage backends, cache servers, and LLM models.

    This unified configuration handles all aspects of how agents access and store data:
    - Storage backend (SQLite database or JSONL files)
    - Cache source (remote BARSUKAS server for translation lookups)
    - LLM model (which model to use for generation)
    """

    def __init__(
        self,
        backend_type: Optional[BackendType] = None,
        sqlite_path: Optional[str] = None,
        jsonl_data_dir: Optional[str] = None,
        barsukas_url: Optional[str] = None,
        cache_only: bool = False,
        model: Optional[str] = None,
    ):
        """Initialize data source configuration.

        Args:
            backend_type: The type of backend to use (defaults to env var or SQLITE)
            sqlite_path: Path to SQLite database file (defaults to constants.WORDFREQ_DB_PATH)
            jsonl_data_dir: Path to JSONL data directory (defaults to data/working)
            barsukas_url: URL of BARSUKAS server for cached translations (e.g., http://server:5000)
            cache_only: If True, only use cached translations and fail if not in cache
            model: LLM model to use (e.g., "gpt-4o-mini", "claude-sonnet-4")
        """
        # Determine backend type from env var or default
        if backend_type is None:
            backend_str = os.environ.get("STORAGE_BACKEND", "sqlite").lower()
            try:
                backend_type = BackendType(backend_str)
            except ValueError:
                raise ValueError(
                    f"Invalid STORAGE_BACKEND: {backend_str}. "
                    f"Must be one of: {[b.value for b in BackendType]}"
                )

        self.backend_type = backend_type

        # Set backend-specific paths
        if self.backend_type == BackendType.SQLITE:
            self.sqlite_path = sqlite_path or constants.WORDFREQ_DB_PATH
            self.jsonl_data_dir = None
        else:  # JSONL
            self.sqlite_path = None
            self.jsonl_data_dir = jsonl_data_dir or os.path.join(
                os.path.dirname(constants.WORDFREQ_DB_PATH), "..", "data", "working"
            )

        # Cache configuration
        self.barsukas_url = barsukas_url.rstrip("/") if barsukas_url else None
        self.cache_only = cache_only

        # Validate cache_only requires barsukas_url
        if self.cache_only and not self.barsukas_url:
            raise ValueError("cache_only=True requires barsukas_url to be specified")

        # LLM configuration
        self.model = model

    @classmethod
    def from_env(cls) -> "DataSourceConfig":
        """Create configuration from environment variables.

        Environment variables:
            STORAGE_BACKEND: "sqlite" or "jsonl" (default: "sqlite")
            SQLITE_DB_PATH: Path to SQLite database (optional)
            JSONL_DATA_DIR: Path to JSONL data directory (optional)
            BARSUKAS_CACHE_URL: URL of BARSUKAS cache server (optional)
            CACHE_ONLY: "true" or "false" (default: "false")
            LLM_MODEL: Default LLM model to use (optional)

        Returns:
            DataSourceConfig instance
        """
        backend_str = os.environ.get("STORAGE_BACKEND", "sqlite").lower()
        backend_type = BackendType(backend_str)

        sqlite_path = os.environ.get("SQLITE_DB_PATH")
        jsonl_data_dir = os.environ.get("JSONL_DATA_DIR")
        barsukas_url = os.environ.get("BARSUKAS_CACHE_URL")
        cache_only = os.environ.get("CACHE_ONLY", "false").lower() == "true"
        model = os.environ.get("LLM_MODEL")

        return cls(
            backend_type=backend_type,
            sqlite_path=sqlite_path,
            jsonl_data_dir=jsonl_data_dir,
            barsukas_url=barsukas_url,
            cache_only=cache_only,
            model=model,
        )

    def __repr__(self) -> str:
        """String representation of config."""
        parts = [f"backend_type={self.backend_type.value.upper()}"]

        if self.backend_type == BackendType.SQLITE:
            parts.append(f"sqlite_path={self.sqlite_path}")
        else:
            parts.append(f"jsonl_data_dir={self.jsonl_data_dir}")

        if self.barsukas_url:
            parts.append(f"barsukas_url={self.barsukas_url}")
        if self.cache_only:
            parts.append("cache_only=True")
        if self.model:
            parts.append(f"model={self.model}")

        return f"DataSourceConfig({', '.join(parts)})"
