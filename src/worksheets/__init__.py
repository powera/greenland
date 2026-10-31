"""Barsukas-only UI integration for printable English learning activities."""

from flask import Flask


def register(app: Flask) -> None:
    """Install the complete worksheets UI with one import in the host app."""
    from worksheets.views import bp

    app.register_blueprint(bp)
