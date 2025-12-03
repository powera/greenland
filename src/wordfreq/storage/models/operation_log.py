#!/usr/bin/python3

"""Database models for tracking operations performed on the wordfreq database."""

import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column
from wordfreq.storage.models.schema import Base


class OperationLog(Base):
    """Model for tracking operations performed on the wordfreq database.

    This table logs all significant operations like translations, imports, and updates.
    The fact field contains structured JSON data about what happened.
    Entity IDs are stored for querying but without foreign keys to avoid impacting other tables.
    """

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "gpt-5-nano", "lokys-agent", "manual-import"
    operation_type: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "translation", "definition", "import"
    timestamp: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), index=True
    )

    # JSON fact containing structured data about what happened
    fact: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string

    # Optional entity references for querying (nullable for flexibility)
    # Note: These are one-way references only - no relationships defined to avoid impacting other tables
    lemma_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    word_token_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    derivative_form_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
