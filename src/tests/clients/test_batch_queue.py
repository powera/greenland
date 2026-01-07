#!/usr/bin/python3
"""Unit tests for batch queue manager."""

import unittest
import json
import tempfile
import os
import sys
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    BatchRequestStatus,
    create_batch_database_session,
)
from clients.openai_batch_client import BatchStatus


class BatchQueueManagerTestCase(unittest.TestCase):
    """Tests for BatchQueueManager."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary database for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create session
        self.session = create_batch_database_session(self.db_path)

        # Create mock batch client
        self.mock_batch_client = Mock()

        # Create manager with mock client
        self.manager = BatchQueueManager(
            db_session=self.session, batch_client=self.mock_batch_client, debug=False
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.session.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_queue_request(self):
        """Test queueing a batch request."""
        metadata = BatchRequestMetadata(
            custom_id="test_request_1",
            agent_name="voras",
            operation_type="validate_translation",
            entity_id=123,
            entity_type="lemma",
            language_code="lt",
        )

        request_body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Test"}]}

        record = self.manager.queue_request(
            custom_id="test_request_1",
            request_body=request_body,
            metadata=metadata,
            endpoint="/v1/chat/completions",
        )

        # Verify record was created
        self.assertIsNotNone(record)
        self.assertEqual(record.custom_id, "test_request_1")
        self.assertEqual(record.agent_name, "voras")
        self.assertEqual(record.operation_type, "validate_translation")
        self.assertEqual(record.status, BatchRequestStatus.PENDING.value)
        self.assertEqual(record.endpoint, "/v1/chat/completions")

        # Verify request body was stored as JSON
        stored_body = json.loads(record.request_body)
        self.assertEqual(stored_body["model"], "gpt-4o-mini")

    def test_queue_request_duplicate_custom_id(self):
        """Test that duplicate custom_id raises an error."""
        metadata = BatchRequestMetadata(
            custom_id="test_request_1", agent_name="voras", operation_type="validate_translation"
        )

        request_body = {"model": "gpt-4o-mini"}

        # Queue first request
        self.manager.queue_request(
            custom_id="test_request_1", request_body=request_body, metadata=metadata
        )

        # Try to queue duplicate - should raise ValueError
        with self.assertRaises(ValueError) as context:
            self.manager.queue_request(
                custom_id="test_request_1", request_body=request_body, metadata=metadata
            )

        self.assertIn("already exists", str(context.exception))

    def test_get_pending_requests(self):
        """Test retrieving pending requests."""
        # Queue multiple requests
        for i in range(3):
            metadata = BatchRequestMetadata(
                custom_id=f"test_request_{i}",
                agent_name="voras",
                operation_type="validate_translation",
            )
            self.manager.queue_request(
                custom_id=f"test_request_{i}",
                request_body={"model": "gpt-4o-mini"},
                metadata=metadata,
            )

        # Get all pending requests
        pending = self.manager.get_pending_requests()
        self.assertEqual(len(pending), 3)

        # Get pending requests filtered by agent
        pending_voras = self.manager.get_pending_requests(agent_name="voras")
        self.assertEqual(len(pending_voras), 3)

        pending_lokys = self.manager.get_pending_requests(agent_name="lokys")
        self.assertEqual(len(pending_lokys), 0)

    def test_submit_batch(self):
        """Test submitting a batch."""
        # Queue some requests
        requests = []
        for i in range(2):
            metadata = BatchRequestMetadata(
                custom_id=f"test_request_{i}",
                agent_name="voras",
                operation_type="validate_translation",
            )
            record = self.manager.queue_request(
                custom_id=f"test_request_{i}",
                request_body={"model": "gpt-4o-mini"},
                metadata=metadata,
            )
            requests.append(record)

        # Mock batch client responses
        self.mock_batch_client.upload_batch_file.return_value = "file_123"
        self.mock_batch_client.create_batch.return_value = {
            "id": "batch_abc",
            "status": "validating",
        }

        # Submit batch
        batch_id, file_id = self.manager.submit_batch(requests, batch_metadata={"agent": "voras"})

        # Verify batch was submitted
        self.assertEqual(batch_id, "batch_abc")
        self.assertEqual(file_id, "file_123")

        # Verify batch client methods were called
        self.mock_batch_client.upload_batch_file.assert_called_once()
        self.mock_batch_client.create_batch.assert_called_once()

        # Verify request statuses were updated
        for req in requests:
            self.session.refresh(req)
            self.assertEqual(req.status, BatchRequestStatus.SUBMITTED.value)
            self.assertEqual(req.batch_id, "batch_abc")
            self.assertEqual(req.batch_file_id, "file_123")
            self.assertIsNotNone(req.submitted_at)

    def test_check_batch_status_in_progress(self):
        """Test checking batch status when in progress."""
        # Queue and submit a request
        metadata = BatchRequestMetadata(
            custom_id="test_request_1", agent_name="voras", operation_type="validate_translation"
        )
        record = self.manager.queue_request(
            custom_id="test_request_1", request_body={"model": "gpt-4o-mini"}, metadata=metadata
        )

        # Manually set to submitted
        record.batch_id = "batch_abc"
        record.status = BatchRequestStatus.SUBMITTED.value
        self.session.commit()

        # Mock batch status response
        self.mock_batch_client.get_batch_status.return_value = {
            "id": "batch_abc",
            "status": BatchStatus.IN_PROGRESS.value,
            "request_counts": {"total": 1, "completed": 0, "failed": 0},
        }

        # Check status
        batch_info = self.manager.check_batch_status("batch_abc")

        # Verify status was returned
        self.assertEqual(batch_info["status"], BatchStatus.IN_PROGRESS.value)

        # Verify request status was updated to processing
        self.session.refresh(record)
        self.assertEqual(record.status, BatchRequestStatus.PROCESSING.value)

    def test_check_batch_status_completed(self):
        """Test checking batch status when completed."""
        # Queue and submit a request
        metadata = BatchRequestMetadata(
            custom_id="test_request_1", agent_name="voras", operation_type="validate_translation"
        )
        record = self.manager.queue_request(
            custom_id="test_request_1", request_body={"model": "gpt-4o-mini"}, metadata=metadata
        )

        # Manually set to submitted
        record.batch_id = "batch_abc"
        record.status = BatchRequestStatus.SUBMITTED.value
        self.session.commit()

        # Mock batch status response
        self.mock_batch_client.get_batch_status.return_value = {
            "id": "batch_abc",
            "status": BatchStatus.COMPLETED.value,
            "request_counts": {"total": 1, "completed": 1, "failed": 0},
            "output_file_id": "file_output_123",
        }

        # Check status
        batch_info = self.manager.check_batch_status("batch_abc")

        # Verify status was returned
        self.assertEqual(batch_info["status"], BatchStatus.COMPLETED.value)

        # Verify request status was updated to processing (ready for retrieval)
        self.session.refresh(record)
        self.assertEqual(record.status, BatchRequestStatus.PROCESSING.value)

    def test_check_batch_status_failed(self):
        """Test checking batch status when failed."""
        # Queue and submit a request
        metadata = BatchRequestMetadata(
            custom_id="test_request_1", agent_name="voras", operation_type="validate_translation"
        )
        record = self.manager.queue_request(
            custom_id="test_request_1", request_body={"model": "gpt-4o-mini"}, metadata=metadata
        )

        # Manually set to submitted
        record.batch_id = "batch_abc"
        record.status = BatchRequestStatus.SUBMITTED.value
        self.session.commit()

        # Mock batch status response
        self.mock_batch_client.get_batch_status.return_value = {
            "id": "batch_abc",
            "status": BatchStatus.FAILED.value,
            "request_counts": {"total": 1, "completed": 0, "failed": 1},
        }

        # Check status
        batch_info = self.manager.check_batch_status("batch_abc")

        # Verify status was returned
        self.assertEqual(batch_info["status"], BatchStatus.FAILED.value)

        # Verify request status was updated to failed
        self.session.refresh(record)
        self.assertEqual(record.status, BatchRequestStatus.FAILED.value)

    def test_retrieve_batch_results(self):
        """Test retrieving batch results."""
        # Queue and submit a request
        metadata = BatchRequestMetadata(
            custom_id="test_request_1",
            agent_name="voras",
            operation_type="validate_translation",
            entity_id=123,
        )
        record = self.manager.queue_request(
            custom_id="test_request_1", request_body={"model": "gpt-4o-mini"}, metadata=metadata
        )

        # Manually set to processing
        record.batch_id = "batch_abc"
        record.status = BatchRequestStatus.PROCESSING.value
        self.session.commit()

        # Mock batch client responses
        self.mock_batch_client.get_batch_status.return_value = {
            "id": "batch_abc",
            "status": BatchStatus.COMPLETED.value,
            "output_file_id": "file_output_123",
        }

        self.mock_batch_client.download_batch_results.return_value = [
            {
                "custom_id": "test_request_1",
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": json.dumps({"result": "success"})}}]
                    },
                },
            }
        ]

        # Retrieve results
        count = self.manager.retrieve_batch_results("batch_abc")

        # Verify results were processed
        self.assertEqual(count, 1)

        # Verify request status was updated
        self.session.refresh(record)
        self.assertEqual(record.status, BatchRequestStatus.COMPLETED.value)
        self.assertIsNotNone(record.response_body)
        self.assertIsNotNone(record.completed_at)

    def test_retrieve_batch_results_with_error(self):
        """Test retrieving batch results with errors."""
        # Queue and submit a request
        metadata = BatchRequestMetadata(
            custom_id="test_request_1", agent_name="voras", operation_type="validate_translation"
        )
        record = self.manager.queue_request(
            custom_id="test_request_1", request_body={"model": "gpt-4o-mini"}, metadata=metadata
        )

        # Manually set to processing
        record.batch_id = "batch_abc"
        record.status = BatchRequestStatus.PROCESSING.value
        self.session.commit()

        # Mock batch client responses
        self.mock_batch_client.get_batch_status.return_value = {
            "id": "batch_abc",
            "status": BatchStatus.COMPLETED.value,
            "output_file_id": "file_output_123",
        }

        self.mock_batch_client.download_batch_results.return_value = [
            {
                "custom_id": "test_request_1",
                "error": {"message": "Rate limit exceeded", "type": "rate_limit_error"},
            }
        ]

        # Retrieve results
        count = self.manager.retrieve_batch_results("batch_abc")

        # Verify results were processed
        self.assertEqual(count, 1)

        # Verify request status was updated to failed
        self.session.refresh(record)
        self.assertEqual(record.status, BatchRequestStatus.FAILED.value)
        self.assertIsNotNone(record.error_message)

    def test_get_completed_requests(self):
        """Test retrieving completed requests."""
        # Create multiple requests with different statuses
        for i, status in enumerate(
            [
                BatchRequestStatus.COMPLETED,
                BatchRequestStatus.COMPLETED,
                BatchRequestStatus.FAILED,
                BatchRequestStatus.PROCESSING,
            ]
        ):
            metadata = BatchRequestMetadata(
                custom_id=f"test_request_{i}",
                agent_name="voras",
                operation_type="validate_translation",
            )
            record = self.manager.queue_request(
                custom_id=f"test_request_{i}",
                request_body={"model": "gpt-4o-mini"},
                metadata=metadata,
            )
            record.status = status.value
            record.batch_id = "batch_abc"
            if status == BatchRequestStatus.COMPLETED:
                record.response_body = json.dumps({"result": "success"})
                record.completed_at = datetime.now()
            self.session.commit()

        # Get completed requests
        completed = self.manager.get_completed_requests(batch_id="batch_abc")
        self.assertEqual(len(completed), 2)

        # Verify all are completed
        for req in completed:
            self.assertEqual(req.status, BatchRequestStatus.COMPLETED.value)
            self.assertIsNotNone(req.response_body)

    def test_get_batch_summary(self):
        """Test getting batch summary."""
        # Create requests with different statuses
        statuses = [
            BatchRequestStatus.SUBMITTED,
            BatchRequestStatus.PROCESSING,
            BatchRequestStatus.COMPLETED,
            BatchRequestStatus.COMPLETED,
            BatchRequestStatus.FAILED,
        ]

        for i, status in enumerate(statuses):
            metadata = BatchRequestMetadata(
                custom_id=f"test_request_{i}",
                agent_name="voras",
                operation_type="validate_translation",
            )
            record = self.manager.queue_request(
                custom_id=f"test_request_{i}",
                request_body={"model": "gpt-4o-mini"},
                metadata=metadata,
            )
            record.status = status.value
            record.batch_id = "batch_abc"
            record.submitted_at = datetime.now()
            if status == BatchRequestStatus.COMPLETED:
                record.completed_at = datetime.now()
            self.session.commit()

        # Get summary
        summary = self.manager.get_batch_summary("batch_abc")

        # Verify summary
        self.assertEqual(summary["batch_id"], "batch_abc")
        self.assertEqual(summary["total_requests"], 5)
        self.assertEqual(summary["status_counts"][BatchRequestStatus.COMPLETED.value], 2)
        self.assertEqual(summary["status_counts"][BatchRequestStatus.SUBMITTED.value], 1)
        self.assertEqual(summary["status_counts"][BatchRequestStatus.PROCESSING.value], 1)
        self.assertEqual(summary["status_counts"][BatchRequestStatus.FAILED.value], 1)

    def test_list_active_batches(self):
        """Test listing active batches."""
        # Create requests for different batches
        for batch_num in range(3):
            for req_num in range(2):
                metadata = BatchRequestMetadata(
                    custom_id=f"batch{batch_num}_req{req_num}",
                    agent_name="voras",
                    operation_type="validate_translation",
                )
                record = self.manager.queue_request(
                    custom_id=f"batch{batch_num}_req{req_num}",
                    request_body={"model": "gpt-4o-mini"},
                    metadata=metadata,
                )
                record.batch_id = f"batch_{batch_num}"

                # Make first two batches active, third completed
                if batch_num < 2:
                    record.status = BatchRequestStatus.PROCESSING.value
                else:
                    record.status = BatchRequestStatus.COMPLETED.value

                self.session.commit()

        # Get active batches
        active = self.manager.list_active_batches()

        # Should only have 2 active batches
        self.assertEqual(len(active), 2)
        self.assertIn("batch_0", active)
        self.assertIn("batch_1", active)
        self.assertNotIn("batch_2", active)


class BatchRequestMetadataTestCase(unittest.TestCase):
    """Tests for BatchRequestMetadata dataclass."""

    def test_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = BatchRequestMetadata(
            custom_id="test_1",
            agent_name="voras",
            operation_type="validate",
            entity_id=123,
            entity_type="lemma",
            language_code="lt",
        )

        data = metadata.to_dict()

        self.assertEqual(data["custom_id"], "test_1")
        self.assertEqual(data["agent_name"], "voras")
        self.assertEqual(data["entity_id"], 123)

    def test_from_dict(self):
        """Test creating metadata from dictionary."""
        data = {
            "custom_id": "test_1",
            "agent_name": "voras",
            "operation_type": "validate",
            "entity_id": 123,
            "extra_field": "ignored",
        }

        metadata = BatchRequestMetadata.from_dict(data)

        self.assertEqual(metadata.custom_id, "test_1")
        self.assertEqual(metadata.agent_name, "voras")
        self.assertEqual(metadata.entity_id, 123)
        # Extra field should be ignored
        self.assertFalse(hasattr(metadata, "extra_field"))


if __name__ == "__main__":
    unittest.main()
