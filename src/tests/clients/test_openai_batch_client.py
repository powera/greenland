#!/usr/bin/python3
"""Unit tests for OpenAI Batch API client."""

import json
import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.openai.batch_client import BatchStatus, OpenAIBatchClient


class OpenAIBatchClientTestCase(unittest.TestCase):
    """Tests for OpenAIBatchClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Create client without API key for testing
        with patch("clients.openai.batch_client.load_key", return_value=None):
            self.client = OpenAIBatchClient(debug=False)

    @patch("clients.openai.batch_client.requests.post")
    def test_upload_batch_file(self, mock_post: MagicMock) -> None:
        """Test uploading a batch file."""
        # Set API key for this test
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "file_abc123",
            "purpose": "batch",
            "filename": "batch_input.jsonl",
        }
        mock_post.return_value = mock_response

        # Create test requests
        requests_data = [
            {
                "custom_id": "request-1",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            }
        ]

        # Upload file
        file_id = self.client.upload_batch_file(requests_data)

        # Verify file ID was returned
        self.assertEqual(file_id, "file_abc123")

        # Verify post was called with correct data
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertIn("files", call_kwargs)
        self.assertEqual(call_kwargs["data"]["purpose"], "batch")

    def test_upload_batch_file_no_api_key(self) -> None:
        """Test that upload fails without API key."""
        requests_data = [{"custom_id": "test"}]

        with self.assertRaises(RuntimeError) as context:
            self.client.upload_batch_file(requests_data)

        self.assertIn("API key not available", str(context.exception))

    @patch("clients.openai.batch_client.requests.post")
    def test_create_batch(self, mock_post: MagicMock) -> None:
        """Test creating a batch."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "batch_abc123",
            "status": "validating",
            "input_file_id": "file_abc123",
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h",
        }
        mock_post.return_value = mock_response

        # Create batch
        batch_info = self.client.create_batch(
            input_file_id="file_abc123", endpoint="/v1/chat/completions", metadata={"test": "value"}
        )

        # Verify batch info was returned
        self.assertEqual(batch_info["id"], "batch_abc123")
        self.assertEqual(batch_info["status"], "validating")

        # Verify post was called with correct payload
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        self.assertEqual(payload["input_file_id"], "file_abc123")
        self.assertEqual(payload["endpoint"], "/v1/chat/completions")
        self.assertEqual(payload["metadata"]["test"], "value")

    @patch("clients.openai.batch_client.requests.get")
    def test_get_batch_status(self, mock_get: MagicMock) -> None:
        """Test getting batch status."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "batch_abc123",
            "status": "in_progress",
            "request_counts": {"total": 100, "completed": 50, "failed": 0},
        }
        mock_get.return_value = mock_response

        # Get status
        batch_info = self.client.get_batch_status("batch_abc123")

        # Verify status was returned
        self.assertEqual(batch_info["id"], "batch_abc123")
        self.assertEqual(batch_info["status"], "in_progress")
        self.assertEqual(batch_info["request_counts"]["completed"], 50)

        # Verify get was called with correct URL
        mock_get.assert_called_once()
        call_args = mock_get.call_args[0]
        self.assertIn("batch_abc123", call_args[0])

    @patch("clients.openai.batch_client.requests.get")
    def test_list_batches(self, mock_get: MagicMock) -> None:
        """Test listing batches."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "batch_1", "status": "completed"},
                {"id": "batch_2", "status": "in_progress"},
            ]
        }
        mock_get.return_value = mock_response

        # List batches
        batches = self.client.list_batches(limit=2)

        # Verify batches were returned
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0]["id"], "batch_1")
        self.assertEqual(batches[1]["id"], "batch_2")

        # Verify get was called with correct params
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["params"]["limit"], 2)

    @patch("clients.openai.batch_client.requests.post")
    def test_cancel_batch(self, mock_post: MagicMock) -> None:
        """Test cancelling a batch."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "batch_abc123", "status": "cancelling"}
        mock_post.return_value = mock_response

        # Cancel batch
        batch_info = self.client.cancel_batch("batch_abc123")

        # Verify status was returned
        self.assertEqual(batch_info["id"], "batch_abc123")
        self.assertEqual(batch_info["status"], "cancelling")

        # Verify post was called with correct URL
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        self.assertIn("batch_abc123", call_args[0])
        self.assertIn("cancel", call_args[0])

    @patch("clients.openai.batch_client.requests.get")
    def test_download_batch_results(self, mock_get: MagicMock) -> None:
        """Test downloading batch results."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response with JSONL data
        jsonl_data = "\n".join(
            [
                json.dumps(
                    {
                        "custom_id": "request-1",
                        "response": {"status_code": 200, "body": {"result": "success"}},
                    }
                ),
                json.dumps(
                    {
                        "custom_id": "request-2",
                        "response": {"status_code": 200, "body": {"result": "success"}},
                    }
                ),
            ]
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = jsonl_data
        mock_get.return_value = mock_response

        # Download results
        results = self.client.download_batch_results("file_output_123")

        # Verify results were parsed
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["custom_id"], "request-1")
        self.assertEqual(results[1]["custom_id"], "request-2")

        # Verify get was called with correct URL
        mock_get.assert_called_once()
        call_args = mock_get.call_args[0]
        self.assertIn("file_output_123", call_args[0])
        self.assertIn("content", call_args[0])

    @patch("clients.openai.batch_client.requests.get")
    @patch("clients.openai.batch_client.time.sleep")
    def test_wait_for_batch_completion(self, mock_sleep: MagicMock, mock_get: MagicMock) -> None:
        """Test waiting for batch completion."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock responses - first in_progress, then completed
        mock_response_in_progress = Mock()
        mock_response_in_progress.status_code = 200
        mock_response_in_progress.json.return_value = {
            "id": "batch_abc123",
            "status": "in_progress",
            "request_counts": {"total": 100, "completed": 50, "failed": 0},
        }

        mock_response_completed = Mock()
        mock_response_completed.status_code = 200
        mock_response_completed.json.return_value = {
            "id": "batch_abc123",
            "status": "completed",
            "request_counts": {"total": 100, "completed": 100, "failed": 0},
            "output_file_id": "file_output_123",
        }

        mock_get.side_effect = [mock_response_in_progress, mock_response_completed]

        # Wait for completion
        batch_info = self.client.wait_for_batch_completion("batch_abc123", poll_interval=1)

        # Verify completed batch was returned
        self.assertEqual(batch_info["status"], "completed")
        self.assertEqual(batch_info["output_file_id"], "file_output_123")

        # Verify get was called twice
        self.assertEqual(mock_get.call_count, 2)

        # Verify sleep was called once (between polls)
        mock_sleep.assert_called_once_with(1)

    @patch("clients.openai.batch_client.requests.get")
    @patch("clients.openai.batch_client.time.sleep")
    def test_wait_for_batch_completion_failure(
        self, mock_sleep: MagicMock, mock_get: MagicMock
    ) -> None:
        """Test waiting for batch that fails."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock response - failed batch
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "batch_abc123",
            "status": "failed",
            "request_counts": {"total": 100, "completed": 50, "failed": 50},
        }
        mock_get.return_value = mock_response

        # Wait for completion - should raise exception
        with self.assertRaises(Exception) as context:
            self.client.wait_for_batch_completion("batch_abc123")

        self.assertIn("failed", str(context.exception))

    @patch("clients.openai.batch_client.requests.post")
    def test_upload_error_handling(self, mock_post: MagicMock) -> None:
        """Test error handling during upload."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        # Try to upload - should raise exception
        requests_data = [{"custom_id": "test"}]
        with self.assertRaises(Exception) as context:
            self.client.upload_batch_file(requests_data)

        self.assertIn("400", str(context.exception))

    @patch("clients.openai.batch_client.requests.get")
    def test_get_status_error_handling(self, mock_get: MagicMock) -> None:
        """Test error handling when getting status."""
        # Set API key
        self.client.api_key = "test_key"
        self.client.headers = {
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        }

        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Batch not found"
        mock_get.return_value = mock_response

        # Try to get status - should raise exception
        with self.assertRaises(Exception) as context:
            self.client.get_batch_status("nonexistent_batch")

        self.assertIn("404", str(context.exception))


class BatchStatusEnumTestCase(unittest.TestCase):
    """Tests for BatchStatus enum."""

    def test_batch_status_values(self) -> None:
        """Test that batch status enum has expected values."""
        self.assertEqual(BatchStatus.VALIDATING.value, "validating")
        self.assertEqual(BatchStatus.FAILED.value, "failed")
        self.assertEqual(BatchStatus.IN_PROGRESS.value, "in_progress")
        self.assertEqual(BatchStatus.FINALIZING.value, "finalizing")
        self.assertEqual(BatchStatus.COMPLETED.value, "completed")
        self.assertEqual(BatchStatus.EXPIRED.value, "expired")
        self.assertEqual(BatchStatus.CANCELLING.value, "cancelling")
        self.assertEqual(BatchStatus.CANCELLED.value, "cancelled")


if __name__ == "__main__":
    unittest.main()
