"""API v1 route registration split across focused modules."""

# Import modules for side-effect route registration.
from barsukas.routes.api import v1_core  # noqa: F401
from barsukas.routes.api import v1_meta  # noqa: F401
from barsukas.routes.api import v1_sentences  # noqa: F401
