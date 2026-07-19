#!/usr/bin/python3

"""
Rapid Review Hub Routes

The rapid review hub has been folded into the Quality Hub; this blueprint
only keeps the old URL working.
"""

from flask import Blueprint, redirect, url_for
from flask.typing import ResponseReturnValue

bp = Blueprint("rapid_review_hub", __name__, url_prefix="/rapid-review")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Redirect to the Quality Hub, which now hosts the rapid review entry points."""
    return redirect(url_for("quality.index"))
