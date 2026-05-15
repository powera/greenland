"""API route registration split across focused modules."""

from barsukas.routes.api import lemma_routes  # noqa: F401
from barsukas.routes.api import meta_routes  # noqa: F401
from barsukas.routes.api import sentence_routes  # noqa: F401
