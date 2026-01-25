#!/usr/bin/python3

"""
Rapid Review Hub Routes

Provides a central hub for accessing all rapid review activities.
"""

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

bp = Blueprint("rapid_review_hub", __name__, url_prefix="/rapid-review")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the rapid review hub with links to all review activities."""
    return render_template("rapid_review_hub/index.html")
