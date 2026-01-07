"""Shared logging configuration for the project.

Provides a simple `configure_logging` helper that sets a standard formatter
including file path and line number, and `get_logger` to obtain loggers.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


class RelPathFormatter(logging.Formatter):
    """Formatter that replaces the absolute pathname with a repo-relative path.

    The repo root is assumed to be two parents above this file (project root).
    If the relative path starts with "src/" it is stripped so logged paths
    look like "agents/sernas/agent.py:123".
    """

    def __init__(self, fmt: str | None = None, repo_root: Path | None = None):
        super().__init__(fmt)
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[1]
        )

    def format(self, record: logging.LogRecord) -> str:
        try:
            p = Path(record.pathname).resolve()
            try:
                rel = p.relative_to(self.repo_root)
            except Exception:
                rel = p
            rel_str = rel.as_posix()
            if rel_str.startswith("src/"):
                rel_str = rel_str[len("src/") :]
            record.__dict__["relpath"] = rel_str
        except Exception:
            record.__dict__["relpath"] = record.pathname

        # If there's exception info, compute where the exception was raised
        try:
            if getattr(record, "exc_info", None) and record.exc_info[2] is not None:
                tb = record.exc_info[2]
                while tb.tb_next is not None:
                    tb = tb.tb_next
                origin_path = Path(tb.tb_frame.f_code.co_filename).resolve()
                try:
                    origin_rel = origin_path.relative_to(self.repo_root)
                except Exception:
                    origin_rel = origin_path
                origin_str = origin_rel.as_posix()
                if origin_str.startswith("src/"):
                    origin_str = origin_str[len("src/") :]
                origin_lineno = tb.tb_lineno
                record.__dict__["exc_origin"] = f" (orig: {origin_str}:{origin_lineno})"
            else:
                record.__dict__["exc_origin"] = ""
        except Exception:
            record.__dict__["exc_origin"] = ""

        return super().format(record)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger once. Safe to call multiple times.

    The format uses `relpath:lineno` instead of an absolute pathname.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    fmt = "%(asctime)s %(levelname)s %(name)s %(relpath)s:%(lineno)d%(exc_origin)s - %(message)s"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RelPathFormatter(fmt))
    root.setLevel(level)
    root.addHandler(handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]
