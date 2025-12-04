"""Base interfaces for storage backends."""

from wordfreq.storage.backend.base.session import BaseSession
from wordfreq.storage.backend.base.query import BaseQuery
from wordfreq.storage.backend.base.storage import BaseStorage

__all__ = ["BaseSession", "BaseQuery", "BaseStorage"]
