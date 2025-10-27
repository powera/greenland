#!/usr/bin/python3
"""Client for interacting with OpenAI Batch API for cost-effective batch processing."""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Any
from enum import Enum

import requests

import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_BASE = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 50

class BatchStatus(Enum):
    """Status of a batch job."""
    VALIDATING = "validating"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class OpenAIBatchClient:
    """Client for making batch requests to OpenAI Batch API.

    The Batch API allows submitting multiple requests at once for processing
    with significant cost savings (typically 50% off) at the expense of latency.
    Batches are processed asynchronously and results are retrieved later.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """Initialize OpenAI Batch client with API key."""
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAIBatchClient in debug mode")
        self.api_key = self._load_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _load_key(self) -> str:
        """Load OpenAI API key from file."""
        key_path = os.path.join(constants.KEY_DIR, "openai.key")
        with open(key_path) as f:
            return f.read().strip()

    def upload_batch_file(self, requests_data: List[Dict[str, Any]]) -> str:
        """Upload a batch input file to OpenAI.

        Args:
            requests_data: List of request dictionaries in JSONL format.
                Each request should have:
                - custom_id: Unique identifier for this request
                - method: HTTP method (usually "POST")
                - url: API endpoint (e.g., "/v1/responses")
                - body: Request body matching the endpoint's schema

        Returns:
            File ID of the uploaded batch file

        Example request format:
            {
                "custom_id": "request-1",
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": "gpt-5-nano",
                    "input": "Translate 'hello' to Spanish",
                    "max_output_tokens": 512
                }
            }
        """
        # Convert list of dicts to JSONL format
        jsonl_content = "\n".join(json.dumps(req) for req in requests_data)

        if self.debug:
            logger.debug(f"Uploading batch file with {len(requests_data)} requests")
            logger.debug(f"First request: {requests_data[0] if requests_data else 'N/A'}")

        # Upload file
        url = f"{API_BASE}/files"
        files = {
            'file': ('batch_input.jsonl', jsonl_content.encode('utf-8'), 'application/jsonl'),
        }
        data = {
            'purpose': 'batch'
        }

        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files=files,
            data=data,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error uploading batch file {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        file_info = response.json()
        file_id = file_info['id']

        if self.debug:
            logger.debug(f"Uploaded batch file: {file_id}")
            logger.debug(f"File info: {file_info}")

        return file_id

    def create_batch(
        self,
        input_file_id: str,
        endpoint: str = "/v1/responses",
        completion_window: str = "24h",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a batch job.

        Args:
            input_file_id: ID of the uploaded batch input file
            endpoint: API endpoint for batch requests (default: /v1/responses)
            completion_window: Time window for completion (default: 24h)
            metadata: Optional metadata to attach to the batch

        Returns:
            Batch object containing id, status, and other metadata
        """
        url = f"{API_BASE}/batches"

        payload = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window
        }

        if metadata:
            payload["metadata"] = metadata

        if self.debug:
            logger.debug(f"Creating batch with input file: {input_file_id}")
            logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error creating batch {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        batch_info = response.json()

        if self.debug:
            logger.debug(f"Created batch: {batch_info['id']}")
            logger.debug(f"Batch info: {batch_info}")

        return batch_info

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Get the current status of a batch job.

        Args:
            batch_id: ID of the batch to check

        Returns:
            Batch object with current status and progress information
        """
        url = f"{API_BASE}/batches/{batch_id}"

        response = requests.get(
            url,
            headers=self.headers,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error getting batch status {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        batch_info = response.json()

        if self.debug:
            logger.debug(f"Batch {batch_id} status: {batch_info.get('status')}")
            logger.debug(f"Progress: {batch_info.get('request_counts', {})}")

        return batch_info

    def list_batches(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent batch jobs.

        Args:
            limit: Maximum number of batches to return (default: 20)

        Returns:
            List of batch objects
        """
        url = f"{API_BASE}/batches"
        params = {"limit": limit}

        response = requests.get(
            url,
            headers=self.headers,
            params=params,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error listing batches {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        batches_data = response.json()
        return batches_data.get('data', [])

    def cancel_batch(self, batch_id: str) -> Dict[str, Any]:
        """Cancel a batch job that is in progress.

        Args:
            batch_id: ID of the batch to cancel

        Returns:
            Updated batch object
        """
        url = f"{API_BASE}/batches/{batch_id}/cancel"

        response = requests.post(
            url,
            headers=self.headers,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error cancelling batch {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        batch_info = response.json()
        logger.info(f"Cancelled batch: {batch_id}")

        return batch_info

    def download_batch_results(self, output_file_id: str) -> List[Dict[str, Any]]:
        """Download and parse batch results.

        Args:
            output_file_id: ID of the output file from a completed batch

        Returns:
            List of result objects, each containing:
            - custom_id: The custom ID from the request
            - response: The API response (or error information)
        """
        url = f"{API_BASE}/files/{output_file_id}/content"

        response = requests.get(
            url,
            headers=self.headers,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Error downloading results {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Parse JSONL response
        results = []
        for line in response.text.strip().split('\n'):
            if line.strip():
                results.append(json.loads(line))

        if self.debug:
            logger.debug(f"Downloaded {len(results)} results")
            if results:
                logger.debug(f"First result: {results[0]}")

        return results

    def wait_for_batch_completion(
        self,
        batch_id: str,
        poll_interval: int = 60,
        max_wait_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """Wait for a batch to complete by polling its status.

        Args:
            batch_id: ID of the batch to monitor
            poll_interval: Seconds between status checks (default: 60)
            max_wait_time: Maximum seconds to wait (default: None = wait indefinitely)

        Returns:
            Final batch object when completed

        Raises:
            Exception if batch fails or expires
            TimeoutError if max_wait_time is exceeded
        """
        start_time = time.time()

        while True:
            batch_info = self.get_batch_status(batch_id)
            status = batch_info['status']

            if status == BatchStatus.COMPLETED.value:
                logger.info(f"Batch {batch_id} completed successfully")
                return batch_info
            elif status in [BatchStatus.FAILED.value, BatchStatus.EXPIRED.value, BatchStatus.CANCELLED.value]:
                error_msg = f"Batch {batch_id} ended with status: {status}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Check timeout
            if max_wait_time and (time.time() - start_time) > max_wait_time:
                raise TimeoutError(f"Batch {batch_id} did not complete within {max_wait_time} seconds")

            # Log progress
            counts = batch_info.get('request_counts', {})
            total = counts.get('total', 0)
            completed = counts.get('completed', 0)
            failed = counts.get('failed', 0)
            logger.info(f"Batch {batch_id} - Status: {status}, Progress: {completed}/{total} completed, {failed} failed")

            # Wait before next poll
            time.sleep(poll_interval)

    def submit_batch_and_wait(
        self,
        requests_data: List[Dict[str, Any]],
        endpoint: str = "/v1/responses",
        metadata: Optional[Dict[str, str]] = None,
        poll_interval: int = 60,
        max_wait_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Convenience method to submit a batch and wait for results.

        Args:
            requests_data: List of batch requests
            endpoint: API endpoint (default: /v1/responses)
            metadata: Optional metadata
            poll_interval: Seconds between status checks
            max_wait_time: Maximum seconds to wait

        Returns:
            List of result objects from the batch
        """
        # Upload batch file
        file_id = self.upload_batch_file(requests_data)
        logger.info(f"Uploaded batch file: {file_id}")

        # Create batch
        batch_info = self.create_batch(file_id, endpoint, metadata=metadata)
        batch_id = batch_info['id']
        logger.info(f"Created batch: {batch_id}")

        # Wait for completion
        completed_batch = self.wait_for_batch_completion(batch_id, poll_interval, max_wait_time)

        # Download results
        output_file_id = completed_batch['output_file_id']
        results = self.download_batch_results(output_file_id)
        logger.info(f"Downloaded {len(results)} results from batch {batch_id}")

        return results


# Create default client instance
client = OpenAIBatchClient(debug=False)

# Expose key functions at module level
def upload_batch_file(requests_data: List[Dict[str, Any]]) -> str:
    """Upload a batch input file to OpenAI."""
    return client.upload_batch_file(requests_data)

def create_batch(
    input_file_id: str,
    endpoint: str = "/v1/responses",
    completion_window: str = "24h",
    metadata: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Create a batch job."""
    return client.create_batch(input_file_id, endpoint, completion_window, metadata)

def get_batch_status(batch_id: str) -> Dict[str, Any]:
    """Get the current status of a batch job."""
    return client.get_batch_status(batch_id)

def list_batches(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent batch jobs."""
    return client.list_batches(limit)

def download_batch_results(output_file_id: str) -> List[Dict[str, Any]]:
    """Download and parse batch results."""
    return client.download_batch_results(output_file_id)

def submit_batch_and_wait(
    requests_data: List[Dict[str, Any]],
    endpoint: str = "/v1/responses",
    metadata: Optional[Dict[str, str]] = None,
    poll_interval: int = 60,
    max_wait_time: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Submit a batch and wait for results."""
    return client.submit_batch_and_wait(requests_data, endpoint, metadata, poll_interval, max_wait_time)
