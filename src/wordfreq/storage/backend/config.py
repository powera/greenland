"""Configuration for storage backends."""

import os
from enum import Enum
from typing import Optional

import constants


class BackendType(Enum):
    """Supported storage backend types."""

    SQLITE = "sqlite"
    JSONL = "jsonl"


class BackendConfig:
    """Configuration for storage backends."""

    def __init__(
        self,
        backend_type: Optional[BackendType] = None,
        sqlite_path: Optional[str] = None,
        jsonl_data_dir: Optional[str] = None,
    ):
        """Initialize backend configuration.

        Args:
            backend_type: The type of backend to use (defaults to env var or SQLITE)
            sqlite_path: Path to SQLite database file (defaults to constants.WORDFREQ_DB_PATH)
            jsonl_data_dir: Path to JSONL data directory (defaults to data/working)
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

    @classmethod
    def from_env(cls) -> "BackendConfig":
        """Create configuration from environment variables.

        Environment variables:
            STORAGE_BACKEND: "sqlite" or "jsonl" (default: "sqlite")
            SQLITE_DB_PATH: Path to SQLite database (optional)
            JSONL_DATA_DIR: Path to JSONL data directory (optional)

        Returns:
            BackendConfig instance
        """
        backend_str = os.environ.get("STORAGE_BACKEND", "sqlite").lower()
        backend_type = BackendType(backend_str)

        sqlite_path = os.environ.get("SQLITE_DB_PATH")
        jsonl_data_dir = os.environ.get("JSONL_DATA_DIR")

        return cls(
            backend_type=backend_type,
            sqlite_path=sqlite_path,
            jsonl_data_dir=jsonl_data_dir,
        )

    def __repr__(self) -> str:
        """String representation of config."""
        if self.backend_type == BackendType.SQLITE:
            return f"BackendConfig(backend_type=SQLITE, sqlite_path={self.sqlite_path})"
        else:
            return f"BackendConfig(backend_type=JSONL, jsonl_data_dir={self.jsonl_data_dir})"
