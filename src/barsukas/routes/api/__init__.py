"""API route package for Barsukas."""

from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api")

# Register route handlers on the shared blueprint
from barsukas.routes.api import html as _html  # noqa: F401
from barsukas.routes.api import v1 as _v1  # noqa: F401
