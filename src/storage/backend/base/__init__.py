"""Base interfaces for storage backends."""

from storage.backend.base.session import BaseSession
from storage.backend.base.storage import BaseStorage

__all__ = ["BaseSession", "BaseStorage"]
