#!/usr/bin/python3

"""Main sync hub route - entry point for all sync operations."""

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

bp = Blueprint("sync_hub", __name__, url_prefix="/sync")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display main sync hub with links to all sync categories."""
    return render_template("sync_hub/index.html")
