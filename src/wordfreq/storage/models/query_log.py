#!/usr/bin/python3

"""Database models for tracking LLM queries for auditing and debugging."""

import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, TIMESTAMP, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from wordfreq.storage.models.schema import Base


class QueryLog(Base):
    """Model for tracking LLM queries for auditing and debugging."""

    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    query_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'definition', 'examples', etc.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
