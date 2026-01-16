"""Configuration for data sources (storage backends, cache, LLM)."""

import os
from enum import Enum
from typing import Optional

import constants
from clients.keys import load_key


class BackendType(Enum):
    """Supported storage backend types."""

    SQLITE = "sqlite"
    JSONL = "jsonl"
    POSTGRES = "postgres"


class DataSourceConfig:
    """Configuration for data sources: storage backends, cache servers, and LLM models.

    This unified configuration handles all aspects of how agents access and store data:
    - Storage backend (SQLite database or JSONL files)
    - Cache source (remote BARSUKAS server for translation lookups)
    - LLM model (which model to use for generation)
    """

    backend_type: BackendType
    sqlite_path: Optional[str]
    jsonl_data_dir: Optional[str]
    postgres_url: Optional[str]
    barsukas_url: Optional[str]
    cache_only: bool
    model: Optional[str]
    debug: bool

    def __init__(
        self,
        backend_type: Optional[BackendType] = None,
        sqlite_path: Optional[str] = None,
        jsonl_data_dir: Optional[str] = None,
        postgres_url: Optional[str] = None,
        barsukas_url: Optional[str] = None,
        cache_only: bool = False,
        model: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize data source configuration.

        Args:
            backend_type: The type of backend to use (defaults to env var or SQLITE)
            sqlite_path: Path to SQLite database file (defaults to constants.WORDFREQ_DB_PATH)
            jsonl_data_dir: Path to JSONL data directory (defaults to data/working)
            postgres_url: PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/db)
            barsukas_url: URL of BARSUKAS server for cached translations (e.g., http://server:5000)
            cache_only: If True, only use cached translations and fail if not in cache
            model: LLM model to use (e.g., "gpt-4o-mini", "claude-sonnet-4")
            debug: Enable debug logging
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
            self.postgres_url = None
        elif self.backend_type == BackendType.POSTGRES:
            if not postgres_url:
                raise ValueError("postgres_url is required for POSTGRES backend")
            self.postgres_url = postgres_url
            self.sqlite_path = None
            self.jsonl_data_dir = None
        else:  # JSONL
            self.sqlite_path = None
            self.jsonl_data_dir = jsonl_data_dir or os.path.join(
                os.path.dirname(constants.WORDFREQ_DB_PATH), "..", "data", "working"
            )
            self.postgres_url = None

        # Cache configuration
        self.barsukas_url = barsukas_url.rstrip("/") if barsukas_url else None
        self.cache_only = cache_only

        # Validate cache_only requires barsukas_url
        if self.cache_only and not self.barsukas_url:
            raise ValueError("cache_only=True requires barsukas_url to be specified")

        # LLM configuration
        self.model = model

        # Debug configuration
        self.debug = debug

    @classmethod
    def from_env(cls) -> "DataSourceConfig":
        """Create configuration from environment variables.

        Environment variables:
            STORAGE_BACKEND: "sqlite", "jsonl", or "postgres" (default: "sqlite")
            SQLITE_DB_PATH: Path to SQLite database (optional)
            JSONL_DATA_DIR: Path to JSONL data directory (optional)
            POSTGRES_URL: PostgreSQL connection URL (optional, built from template if not set)
            BARSUKAS_CACHE_URL: URL of BARSUKAS cache server (optional)
            CACHE_ONLY: "true" or "false" (default: "false")
            LLM_MODEL: Default LLM model to use (optional)
            DEBUG: "true" or "false" (default: "false")

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
        debug = os.environ.get("DEBUG", "false").lower() == "true"

        # Handle PostgreSQL URL
        postgres_url = None
        if backend_type == BackendType.POSTGRES:
            postgres_url = os.environ.get("POSTGRES_URL")
            if not postgres_url:
                # Build from template + key file
                postgres_url = cls.build_postgres_url()

        return cls(
            backend_type=backend_type,
            sqlite_path=sqlite_path,
            jsonl_data_dir=jsonl_data_dir,
            postgres_url=postgres_url,
            barsukas_url=barsukas_url,
            cache_only=cache_only,
            model=model,
            debug=debug,
        )

    @classmethod
    def build_postgres_url(cls, template_path: Optional[str] = None) -> str:
        """Build PostgreSQL URL by combining template with password from key file.

        Args:
            template_path: Path to URL template file (default: PROJECT_ROOT/postgres_ul)

        Returns:
            Complete PostgreSQL connection URL

        Raises:
            ValueError: If template or password file not found
        """
        # Default template path
        if template_path is None:
            template_path = os.path.join(constants.PROJECT_ROOT, "postgres_ul")

        # Load URL template
        if not os.path.exists(template_path):
            raise ValueError(f"PostgreSQL URL template not found at {template_path}")

        with open(template_path) as f:
            url_template = f.read().strip()

        # Load password (required=True raises RuntimeError if not found)
        password = load_key("postgres", required=True)
        assert password is not None  # satisfied by required=True

        # Replace placeholder with actual password
        if "[YOUR-PASSWORD]" not in url_template:
            raise ValueError("PostgreSQL URL template must contain [YOUR-PASSWORD] placeholder")

        return url_template.replace("[YOUR-PASSWORD]", password)

    def __repr__(self) -> str:
        """String representation of config."""
        parts = [f"backend_type={self.backend_type.value.upper()}"]

        if self.backend_type == BackendType.SQLITE:
            parts.append(f"sqlite_path={self.sqlite_path}")
        elif self.backend_type == BackendType.POSTGRES:
            # Mask password in URL for repr
            url = self.postgres_url or ""
            if "@" in url:
                # Show host but mask credentials
                prefix, rest = url.split("@", 1)
                parts.append(f"postgres_url=postgresql://***@{rest}")
            else:
                parts.append(f"postgres_url={url}")
        else:
            parts.append(f"jsonl_data_dir={self.jsonl_data_dir}")

        if self.barsukas_url:
            parts.append(f"barsukas_url={self.barsukas_url}")
        if self.cache_only:
            parts.append("cache_only=True")
        if self.model:
            parts.append(f"model={self.model}")
        if self.debug:
            parts.append("debug=True")

        return f"DataSourceConfig({', '.join(parts)})"
