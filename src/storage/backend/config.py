"""Configuration for data sources (storage backends, cache, LLM)."""

import os
import socket
from enum import Enum
from typing import Optional

import constants
from clients.keys import load_key

# Cached result of IPv6 reachability check (None = not yet checked)
_ipv6_reachable_cache: Optional[bool] = None


def _is_ipv6_reachable() -> bool:
    """Check if the Supabase direct host is reachable via IPv6.

    Attempts a TCP connection to the Supabase direct-connection host using the
    IPv6 address family.  The result is cached so subsequent calls are free.

    Returns:
        True if an IPv6 connection could be established, False otherwise.
    """
    global _ipv6_reachable_cache
    if _ipv6_reachable_cache is not None:
        return _ipv6_reachable_cache

    host = "db.srouvwdghrmwkxnzyzqz.supabase.co"
    port = 5432
    reachable = False
    try:
        addrs = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
        if addrs:
            af, socktype, proto, _canonname, sockaddr = addrs[0]
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(3.0)
            try:
                sock.connect(sockaddr)
                reachable = True
            except (OSError, socket.error):
                reachable = False
            finally:
                sock.close()
    except (socket.gaierror, OSError):
        reachable = False

    _ipv6_reachable_cache = reachable
    return reachable


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
    - LLM API keys (optional, for API server use - avoids command-line exposure)
    """

    backend_type: BackendType
    sqlite_path: Optional[str]
    jsonl_data_dir: Optional[str]
    postgres_url: Optional[str]
    barsukas_url: Optional[str]
    cache_only: bool
    model: Optional[str]
    debug: bool
    # Optional API keys for runtime injection (used by API server)
    openai_api_key: Optional[str]
    anthropic_api_key: Optional[str]
    google_api_key: Optional[str]

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
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
    ):
        """Initialize data source configuration.

        Args:
            backend_type: The type of backend to use (defaults to env var or SQLITE)
            sqlite_path: Path to SQLite database file (defaults to constants.WORDFREQ_DB_PATH)
            jsonl_data_dir: Path to JSONL data directory (defaults to data/working)
            postgres_url: PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/db)
            barsukas_url: URL of BARSUKAS server for cached translations (e.g., http://server:5000)
            cache_only: If True, only use cached translations and fail if not in cache
            model: LLM model to use (e.g., "gpt-5.4-mini", "claude-sonnet-4")
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

        # Optional API keys for runtime injection (used by API server)
        # These allow passing API keys via JSON parameters without command-line exposure
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key
        self.google_api_key = google_api_key

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
    def build_postgres_url(cls) -> str:
        """Build PostgreSQL URL by combining template with password from key file.

        Uses the URL template from constants.POSTGRES_URL_TEMPLATE and sets the
        schema to constants.POSTGRES_SCHEMA via the options parameter.

        If the Supabase direct host is not reachable via IPv6, automatically falls
        back to constants.POSTGRES_POOLER_URL_TEMPLATE (the shared pooler, which
        uses IPv4) so the application works in IPv4-only environments.

        Returns:
            Complete PostgreSQL connection URL with schema configured

        Raises:
            ValueError: If password file not found or template invalid
        """
        # Load password (required=True raises RuntimeError if not found)
        password = load_key("postgres", required=True)
        assert password is not None  # satisfied by required=True

        # Choose between direct (IPv6) and shared pooler (IPv4) URL
        if _is_ipv6_reachable():
            url_template = constants.POSTGRES_URL_TEMPLATE
        else:
            url_template = constants.POSTGRES_POOLER_URL_TEMPLATE

        # Replace placeholder with actual password
        if "[YOUR-PASSWORD]" not in url_template:
            raise ValueError("PostgreSQL URL template must contain [YOUR-PASSWORD] placeholder")

        url = url_template.replace("[YOUR-PASSWORD]", password)

        # Add schema via options parameter
        schema = constants.POSTGRES_SCHEMA
        if "?" in url:
            url = f"{url}&options=-csearch_path%3D{schema}"
        else:
            url = f"{url}?options=-csearch_path%3D{schema}"

        return url

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
        # Show that API keys are set (but don't reveal values)
        if self.openai_api_key:
            parts.append("openai_api_key=***")
        if self.anthropic_api_key:
            parts.append("anthropic_api_key=***")
        if self.google_api_key:
            parts.append("google_api_key=***")

        return f"DataSourceConfig({', '.join(parts)})"
