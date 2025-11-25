#!/usr/bin/python3
"""Batch queue manager for coordinating batch API requests across the application.

This module manages the lifecycle of batch requests:
1. Queue requests for batching
2. Submit batches to OpenAI
3. Track batch status
4. Retrieve and distribute results

Uses a separate SQLite database for tracking batch requests.
"""

import json
import logging
import datetime
import os
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, asdict

from sqlalchemy import String, Text, Integer, TIMESTAMP, func, Index, create_engine
from sqlalchemy.orm import Mapped, mapped_column, Session, DeclarativeBase, sessionmaker

from clients.openai_batch_client import OpenAIBatchClient, BatchStatus
import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Batch tracking database path
BATCH_DB_PATH = os.path.join(constants.SRC_DIR, "clients", "data", "batch_tracking.sqlite")


class Base(DeclarativeBase):
    """Base class for batch tracking database models."""
    pass


class BatchRequestStatus(Enum):
    """Status of individual requests within a batch."""
    PENDING = "pending"  # Request created, not yet submitted
    QUEUED = "queued"  # Request added to a batch file
    SUBMITTED = "submitted"  # Batch has been submitted to OpenAI
    PROCESSING = "processing"  # Batch is being processed
    COMPLETED = "completed"  # Request completed successfully
    FAILED = "failed"  # Request failed
    CANCELLED = "cancelled"  # Request cancelled


@dataclass
class BatchRequestMetadata:
    """Metadata for a batch request."""
    custom_id: str
    agent_name: str  # e.g., "voras", "lokys"
    operation_type: str  # e.g., "validate_translation", "validate_lemma"
    entity_id: Optional[int] = None  # lemma_id, word_token_id, etc.
    entity_type: Optional[str] = None  # "lemma", "word_token", etc.
    language_code: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchRequestMetadata":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class BatchQueue(Base):
    """Database model for tracking batch requests."""
    __tablename__ = "batch_queue"
    __table_args__ = (
        Index("ix_batch_queue_batch_id", "batch_id"),
        Index("ix_batch_queue_status", "status"),
        Index("ix_batch_queue_custom_id", "custom_id"),
        Index("ix_batch_queue_agent_name", "agent_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Request identification
    custom_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # OpenAI batch ID
    batch_file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # OpenAI file ID for input

    # Request content
    request_body: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string of the request body
    endpoint: Mapped[str] = mapped_column(String, nullable=False, default="/v1/responses")

    # Status tracking
    status: Mapped[str] = mapped_column(String, nullable=False, default=BatchRequestStatus.PENDING.value, index=True)

    # Response data
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string of the response
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata for organization and querying
    agent_name: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "voras", "lokys"
    operation_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "validate_translation"
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # Reference to lemma, word_token, etc.
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "lemma", "word_token", etc.
    language_code: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    additional_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Additional JSON metadata

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), index=True)
    submitted_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, nullable=True)


class BatchQueueManager:
    """Manager for batch request queue and lifecycle."""

    def __init__(self, db_session: Session, batch_client: Optional[OpenAIBatchClient] = None, debug: bool = False):
        """Initialize batch queue manager.

        Args:
            db_session: SQLAlchemy database session
            batch_client: Optional OpenAI batch client (creates default if not provided)
            debug: Enable debug logging
        """
        self.db = db_session
        self.batch_client = batch_client or OpenAIBatchClient(debug=debug)
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

    def queue_request(
        self,
        custom_id: str,
        request_body: Dict[str, Any],
        metadata: BatchRequestMetadata,
        endpoint: str = "/v1/responses"
    ) -> BatchQueue:
        """Add a request to the batch queue.

        Args:
            custom_id: Unique identifier for this request
            request_body: Request body matching the API endpoint schema
            metadata: Request metadata for tracking
            endpoint: API endpoint (default: /v1/responses)

        Returns:
            BatchQueue record
        """
        # Check if custom_id already exists
        existing = self.db.query(BatchQueue).filter_by(custom_id=custom_id).first()
        if existing:
            raise ValueError(f"Request with custom_id '{custom_id}' already exists")

        record = BatchQueue(
            custom_id=custom_id,
            request_body=json.dumps(request_body),
            endpoint=endpoint,
            status=BatchRequestStatus.PENDING.value,
            agent_name=metadata.agent_name,
            operation_type=metadata.operation_type,
            entity_id=metadata.entity_id,
            entity_type=metadata.entity_type,
            language_code=metadata.language_code,
            additional_metadata=json.dumps(metadata.to_dict())
        )

        self.db.add(record)
        self.db.commit()

        if self.debug:
            logger.debug(f"Queued request {custom_id} for {metadata.agent_name}/{metadata.operation_type}")

        return record

    def get_pending_requests(
        self,
        agent_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[BatchQueue]:
        """Get pending requests from the queue.

        Args:
            agent_name: Filter by agent name
            operation_type: Filter by operation type
            limit: Maximum number of requests to return

        Returns:
            List of pending BatchQueue records
        """
        query = self.db.query(BatchQueue).filter_by(status=BatchRequestStatus.PENDING.value)

        if agent_name:
            query = query.filter_by(agent_name=agent_name)
        if operation_type:
            query = query.filter_by(operation_type=operation_type)
        if limit:
            query = query.limit(limit)

        return query.all()

    def submit_batch(
        self,
        requests: List[BatchQueue],
        batch_metadata: Optional[Dict[str, str]] = None
    ) -> Tuple[str, str]:
        """Submit a batch of queued requests to OpenAI.

        Args:
            requests: List of BatchQueue records to submit
            batch_metadata: Optional metadata to attach to the batch

        Returns:
            Tuple of (batch_id, file_id)
        """
        if not requests:
            raise ValueError("No requests to submit")

        # Format requests for batch API
        batch_requests = []
        for req in requests:
            batch_requests.append({
                "custom_id": req.custom_id,
                "method": "POST",
                "url": req.endpoint,
                "body": json.loads(req.request_body)
            })

        # Upload batch file
        file_id = self.batch_client.upload_batch_file(batch_requests)
        logger.info(f"Uploaded batch file {file_id} with {len(batch_requests)} requests")

        # Create batch
        endpoint = requests[0].endpoint  # All requests should have same endpoint
        batch_info = self.batch_client.create_batch(file_id, endpoint, metadata=batch_metadata)
        batch_id = batch_info["id"]
        logger.info(f"Created batch {batch_id}")

        # Update request records
        submitted_at = datetime.datetime.now()
        for req in requests:
            req.batch_id = batch_id
            req.batch_file_id = file_id
            req.status = BatchRequestStatus.SUBMITTED.value
            req.submitted_at = submitted_at

        self.db.commit()

        return batch_id, file_id

    def check_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Check the status of a submitted batch.

        Args:
            batch_id: OpenAI batch ID

        Returns:
            Batch status information from OpenAI
        """
        batch_info = self.batch_client.get_batch_status(batch_id)
        status = batch_info["status"]

        # Update request statuses if batch is processing or completed
        if status in [BatchStatus.IN_PROGRESS.value, BatchStatus.FINALIZING.value]:
            self.db.query(BatchQueue).filter_by(
                batch_id=batch_id,
                status=BatchRequestStatus.SUBMITTED.value
            ).update({
                "status": BatchRequestStatus.PROCESSING.value
            })
            self.db.commit()

        return batch_info

    def retrieve_batch_results(self, batch_id: str) -> int:
        """Retrieve and store results from a completed batch.

        Args:
            batch_id: OpenAI batch ID

        Returns:
            Number of results processed
        """
        # Check batch status first
        batch_info = self.batch_client.get_batch_status(batch_id)
        status = batch_info["status"]

        if status != BatchStatus.COMPLETED.value:
            raise ValueError(f"Batch {batch_id} is not completed (status: {status})")

        # Download results
        output_file_id = batch_info["output_file_id"]
        results = self.batch_client.download_batch_results(output_file_id)
        logger.info(f"Downloaded {len(results)} results from batch {batch_id}")

        # Update request records with results
        completed_at = datetime.datetime.now()
        processed_count = 0

        for result in results:
            custom_id = result["custom_id"]

            # Find the request record
            req = self.db.query(BatchQueue).filter_by(custom_id=custom_id).first()
            if not req:
                logger.warning(f"No request record found for custom_id: {custom_id}")
                continue

            # Check if request succeeded or failed
            if result.get("error"):
                req.status = BatchRequestStatus.FAILED.value
                req.error_message = json.dumps(result["error"])
            else:
                req.status = BatchRequestStatus.COMPLETED.value
                req.response_body = json.dumps(result.get("response", {}))

            req.completed_at = completed_at
            processed_count += 1

        self.db.commit()
        logger.info(f"Processed {processed_count} results for batch {batch_id}")

        return processed_count

    def get_completed_requests(
        self,
        agent_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        batch_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[BatchQueue]:
        """Get completed requests with results.

        Args:
            agent_name: Filter by agent name
            operation_type: Filter by operation type
            batch_id: Filter by batch ID
            limit: Maximum number of requests to return

        Returns:
            List of completed BatchQueue records
        """
        query = self.db.query(BatchQueue).filter_by(status=BatchRequestStatus.COMPLETED.value)

        if agent_name:
            query = query.filter_by(agent_name=agent_name)
        if operation_type:
            query = query.filter_by(operation_type=operation_type)
        if batch_id:
            query = query.filter_by(batch_id=batch_id)
        if limit:
            query = query.limit(limit)

        return query.order_by(BatchQueue.completed_at.desc()).all()

    def get_failed_requests(
        self,
        agent_name: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> List[BatchQueue]:
        """Get failed requests.

        Args:
            agent_name: Filter by agent name
            batch_id: Filter by batch ID

        Returns:
            List of failed BatchQueue records
        """
        query = self.db.query(BatchQueue).filter_by(status=BatchRequestStatus.FAILED.value)

        if agent_name:
            query = query.filter_by(agent_name=agent_name)
        if batch_id:
            query = query.filter_by(batch_id=batch_id)

        return query.all()

    def cancel_batch(self, batch_id: str) -> Dict[str, Any]:
        """Cancel a batch that is in progress.

        Args:
            batch_id: OpenAI batch ID

        Returns:
            Batch cancellation information
        """
        # Cancel with OpenAI
        batch_info = self.batch_client.cancel_batch(batch_id)

        # Update request records
        self.db.query(BatchQueue).filter_by(batch_id=batch_id).update({
            "status": BatchRequestStatus.CANCELLED.value
        })
        self.db.commit()

        logger.info(f"Cancelled batch {batch_id}")
        return batch_info

    def get_batch_summary(self, batch_id: str) -> Dict[str, Any]:
        """Get a summary of a batch's requests.

        Args:
            batch_id: OpenAI batch ID

        Returns:
            Dictionary with batch statistics
        """
        requests = self.db.query(BatchQueue).filter_by(batch_id=batch_id).all()

        status_counts = {}
        for req in requests:
            status = req.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "batch_id": batch_id,
            "total_requests": len(requests),
            "status_counts": status_counts,
            "first_submitted": min((r.submitted_at for r in requests if r.submitted_at), default=None),
            "last_completed": max((r.completed_at for r in requests if r.completed_at), default=None)
        }

    def list_active_batches(self) -> List[str]:
        """Get list of active batch IDs.

        Returns:
            List of batch IDs that are submitted or processing
        """
        active_statuses = [
            BatchRequestStatus.SUBMITTED.value,
            BatchRequestStatus.PROCESSING.value
        ]

        result = self.db.query(BatchQueue.batch_id).filter(
            BatchQueue.batch_id.isnot(None),
            BatchQueue.status.in_(active_statuses)
        ).distinct().all()

        return [batch_id for (batch_id,) in result]


def create_batch_database_session(db_path: str = BATCH_DB_PATH) -> Session:
    """Create a new batch tracking database session.

    Args:
        db_path: Path to the batch tracking database

    Returns:
        SQLAlchemy session for the batch tracking database
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Create engine and tables
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

    # Create session
    Session = sessionmaker(bind=engine)
    return Session()


def get_batch_manager(db_session: Optional[Session] = None, debug: bool = False) -> BatchQueueManager:
    """Get a BatchQueueManager instance.

    Args:
        db_session: Optional database session (creates new one if not provided)
        debug: Enable debug logging

    Returns:
        BatchQueueManager instance
    """
    if db_session is None:
        db_session = create_batch_database_session()

    return BatchQueueManager(db_session, debug=debug)
