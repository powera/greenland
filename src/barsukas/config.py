#!/usr/bin/python3

"""Configuration for Barsukas web interface."""

import os
from pathlib import Path

import constants


class Config:
    """Application configuration."""

    # Flask settings
    SECRET_KEY = os.environ.get("BARSUKAS_SECRET_KEY", "dev-secret-key-change-in-production")

    # Server settings
    HOST = os.environ.get("BARSUKAS_HOST", "127.0.0.1")  # Localhost only by default
    PORT = int(os.environ.get("BARSUKAS_PORT", os.environ.get("PORT", 5555)))
    DEBUG = os.environ.get("BARSUKAS_DEBUG", "False").lower() == "true"

    # Database settings
    BASE_DIR = Path(__file__).parent.parent.parent  # repo root
    DEFAULT_DB_PATH = BASE_DIR / "data" / "wordfreq" / "linguistics.sqlite"
    DB_PATH = os.environ.get("BARSUKAS_DB_PATH", str(DEFAULT_DB_PATH))

    # Pagination
    ITEMS_PER_PAGE = 50

    # Operation log settings
    OPERATION_LOG_SOURCE = "barsukas-web-interface"

    # Validation settings
    MIN_DIFFICULTY_LEVEL = constants.MIN_DIFFICULTY_LEVEL
    MAX_DIFFICULTY_LEVEL = constants.MAX_DIFFICULTY_LEVEL
    EXCLUDE_DIFFICULTY_LEVEL = constants.EXCLUDE_DIFFICULTY_LEVEL

    # Access control
    READONLY = False  # Can be overridden at runtime

    # Audio settings
    AUDIO_BASE_DIR = os.environ.get(
        "BARSUKAS_AUDIO_DIR", str(BASE_DIR.parent / "wireword-audio" / "trakaido")
    )

    # S3/CDN settings for audio
    S3_CDN_BASE_URL = os.environ.get(
        "S3_CDN_BASE_URL", "https://trakaido-audio.sfo3.cdn.digitaloceanspaces.com"
    )
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "trakaido-audio")
