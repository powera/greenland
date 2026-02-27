#!/usr/bin/python3

"""Client for interacting with LMStudio API with optional two-phase responses."""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import requests
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException

import clients.lib
from clients.types import Response
from util.telemetry import LLMUsage

# Configure logging with DEBUG level option
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SERVER = "100.118.20.30"
PORT = 9054
DEFAULT_MODEL = (
    "lmstudio-community/Qwen3-4B-GGUF"  # Newer default under 8B params for lower memory pressure.
)
DEFAULT_TIMEOUT = 250
MODEL_OPERATION_TIMEOUT = 30
MODEL_OPERATION_RETRIES = 3
MODEL_OPERATION_RETRY_DELAY = 1.0


class LMStudioError(Exception):
    """Base exception for LMStudio client errors."""

    pass


class LMStudioTimeoutError(LMStudioError):
    """Raised when an LMStudio request times out."""

    pass


class LMStudioRequestError(LMStudioError):
    """Raised when an LMStudio request fails."""

    pass


class LMStudioClient:
    """Client for making requests to LMStudio API with optional two-phase responses."""

    def __init__(
        self,
        server: str = SERVER,
        port: int = PORT,
        timeout: int = DEFAULT_TIMEOUT,
        debug: bool = False,
    ):
        self.server = server
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{server}:{port}/v1"
        self.debug = debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def _make_request(self, endpoint: str, data: Dict) -> requests.Response:
        """Make HTTP request to LMStudio API."""
        url = f"{self.base_url}/{endpoint}"

        if self.debug:
            logger.debug("Request to %s: %s", url, json.dumps(data, indent=2))

        try:
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response

        except requests.exceptions.ConnectTimeout:
            raise LMStudioTimeoutError(f"Connection timed out after {self.timeout}s")
        except requests.exceptions.ReadTimeout:
            raise LMStudioTimeoutError(f"Response timed out after {self.timeout}s")
        except RequestException as e:
            if e.response is not None:
                error_msg = f"Error {e.response.status_code}: {e.response.text}"
            else:
                error_msg = str(e)
            raise LMStudioRequestError(error_msg) from e

    def _process_chat_response(
        self, response: requests.Response, model: str
    ) -> tuple[str, Optional[LLMUsage], Optional[str]]:
        """Process chat response and extract content, usage info, and additional thoughts."""
        result = ""
        usage: Optional[LLMUsage] = None
        additional_thought = None

        # Pattern to extract content within <think> tags
        think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)

        try:
            response_data = response.json()

            # Extract the message content from the choices array
            content = ""
            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message", {})
                content = message.get("content", "")

            # Check for <think> tags
            think_match = think_pattern.search(content)
            while think_match:
                # Extract thought content
                thought_content = think_match.group(1).strip()
                if additional_thought is None:
                    additional_thought = thought_content
                else:
                    additional_thought += " " + thought_content

                # Remove <think> tags and their content from the response
                content = content.replace(f"<think>{think_match.group(1)}</think>", "")

                # Check for additional <think> tags
                think_match = think_pattern.search(content)

            # Clean up markdown code blocks if present
            if content.startswith("```"):
                # Remove the first line (```json)
                content_lines = content.split("\n")
                # Remove the first and last lines if they contain backticks
                if content_lines[0].startswith("```"):
                    content_lines = content_lines[1:]
                if content_lines and content_lines[-1].strip() == "```":
                    content_lines = content_lines[:-1]
                content = "\n".join(content_lines)

            result = content

            # Extract usage information for telemetry
            if "usage" in response_data:
                usage_data = response_data["usage"]
                # Convert to the format expected by LLMUsage.from_api_response
                converted_usage = {
                    "prompt_tokens": usage_data.get("prompt_tokens", 0),
                    "completion_tokens": usage_data.get("completion_tokens", 0),
                    "total_duration": response.elapsed.total_seconds() * 1000,  # Convert to ms
                }
                usage = LLMUsage.from_api_response(converted_usage, model=model)

            if self.debug and additional_thought:
                print("Thought process:", additional_thought)

            return result, usage, additional_thought

        except ValueError as e:
            # Handle JSON parsing errors
            print(f"Error parsing response: {e}")
            return "", None, None

    def warm_model(self, model: str) -> bool:
        """Load model into memory using LM Studio's model load endpoint."""
        url = f"http://{self.server}:{self.port}/api/v1/models/load"
        return self._run_model_operation(
            operation_name="load",
            url=url,
            payload={"model": model},
            verify_loaded=True,
            model=model,
        )

    def unload_model(self, model: str) -> bool:
        """Unload model from memory using LM Studio's model unload endpoint."""
        url = f"http://{self.server}:{self.port}/api/v1/models/unload"
        unload_payload = {
            # Some LM Studio versions expect one field or the other.
            "instance_id": model,
            "model": model,
        }
        return self._run_model_operation(
            operation_name="unload",
            url=url,
            payload=unload_payload,
            verify_loaded=False,
            model=model,
        )

    def _run_model_operation(
        self,
        operation_name: str,
        url: str,
        payload: Dict[str, str],
        verify_loaded: bool,
        model: str,
    ) -> bool:
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)
        for attempt_number in range(1, MODEL_OPERATION_RETRIES + 1):
            try:
                if self.debug:
                    logger.debug(
                        "%s model via %s (attempt %s/%s): %s",
                        operation_name.capitalize(),
                        url,
                        attempt_number,
                        MODEL_OPERATION_RETRIES,
                        payload,
                    )

                response = requests.post(url, json=payload, timeout=operation_timeout)
                if self.debug:
                    logger.debug(
                        "%s response: %s %s",
                        operation_name.capitalize(),
                        response.status_code,
                        response.text,
                    )

                if self._is_successful_model_operation_response(response, operation_name):
                    return True
            except (ConnectTimeout, ReadTimeout):
                if self.debug:
                    logger.debug(
                        "%s timed out on attempt %s/%s",
                        operation_name.capitalize(),
                        attempt_number,
                        MODEL_OPERATION_RETRIES,
                    )
            except RequestException as exc:
                if self.debug:
                    logger.debug(
                        "%s failed on attempt %s/%s: %s",
                        operation_name.capitalize(),
                        attempt_number,
                        MODEL_OPERATION_RETRIES,
                        exc,
                    )

            is_model_loaded = self._is_model_loaded(model)
            if is_model_loaded is not None and is_model_loaded == verify_loaded:
                return True

            if attempt_number < MODEL_OPERATION_RETRIES:
                time.sleep(MODEL_OPERATION_RETRY_DELAY * attempt_number)

        return False

    def _is_successful_model_operation_response(
        self, response: requests.Response, operation_name: str
    ) -> bool:
        if 200 <= response.status_code < 300:
            return True

        response_text = response.text.lower()
        if operation_name == "load":
            return "already loaded" in response_text
        if operation_name == "unload":
            return "not loaded" in response_text or "already unloaded" in response_text
        return False

    def _is_model_loaded(self, model: str) -> Optional[bool]:
        model_endpoints = [
            f"http://{self.server}:{self.port}/v1/models",
            f"http://{self.server}:{self.port}/api/v1/models",
        ]
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)

        for endpoint_url in model_endpoints:
            try:
                response = requests.get(endpoint_url, timeout=operation_timeout)
                if not response.ok:
                    continue

                response_data = response.json()
                model_entries = response_data.get("data", [])
                if not isinstance(model_entries, list):
                    continue

                for model_entry in model_entries:
                    if not isinstance(model_entry, dict):
                        continue
                    model_id = model_entry.get("id")
                    instance_id = model_entry.get("instance_id")
                    loaded_model = model_entry.get("model")

                    candidate_ids = [model_id, instance_id, loaded_model]
                    if any(candidate_id == model for candidate_id in candidate_ids):
                        return True
                    if any(
                        isinstance(candidate_id, str) and candidate_id.endswith(f"/{model}")
                        for candidate_id in candidate_ids
                    ):
                        return True

                return False
            except RequestException:
                continue
            except ValueError:
                continue

        return None

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
    ) -> Response:
        """
        Generate chat completion using LMStudio API.

        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt

        Returns:
            Response data class

        Raises:
            LMStudioTimeoutError: If request times out
            LMStudioRequestError: If request fails
        """
        if self.debug:
            logger.debug(
                "Chat request: model=%s, brief=%s, schema=%s", model, brief, bool(json_schema)
            )

        # Phase 1: Get response (either free-form or JSON)
        messages = []
        if context:
            messages.append({"role": "system", "content": context})

        if json_schema:
            if isinstance(json_schema, clients.lib.Schema):
                schema_obj = json_schema
            else:
                schema_obj = clients.lib.schema_from_dict(json_schema)

            clean_schema = clients.lib.to_ollama_schema(schema_obj)

            # Keep schema guidance concise. The full JSON schema is already sent
            # in response_format.json_schema.schema below.
            schema_prompt = "Match the response schema."

            messages.append({"role": "user", "content": schema_prompt})
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        data = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        if brief:
            data["max_tokens"] = 256

        if json_schema:
            data["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "Details",
                    "description": "N/A",
                    "strict": True,
                    "schema": clean_schema,
                },
            }

        response = self._make_request("chat/completions", data)
        response_text, response_usage, additional_thought = self._process_chat_response(
            response, model
        )

        # Handle JSON responses
        if json_schema:
            # Single-phase JSON response
            try:
                structured_response = json.loads(response_text)
                if self.debug:
                    print(json.dumps(structured_response, indent=2))

                return Response(
                    response_text="",
                    structured_data=structured_response,
                    usage=response_usage,
                    additional_thought=additional_thought,
                )
            except json.JSONDecodeError:
                return Response(
                    response_text="",
                    structured_data={"error": f"Failed to parse JSON: {response_text}"},
                    usage=response_usage,
                    additional_thought=additional_thought,
                )
        else:
            # Text-only response
            if self.debug:
                print(response_text)
            return Response(
                response_text=response_text,
                structured_data={},
                usage=response_usage,
                additional_thought=additional_thought,
            )


# Lazy client instance - only created when first accessed
_client: Optional[LMStudioClient] = None


def _get_client() -> LMStudioClient:
    """Get or create the default client instance."""
    global _client
    if _client is None:
        _client = LMStudioClient(debug=False)
    return _client


# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return _get_client().warm_model(model)


def unload_model(model: str) -> bool:
    return _get_client().unload_model(model)


def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Any] = None,
    context: Optional[str] = None,
) -> Response:
    """
    Generate a chat response.

    Returns:
        Response data class containing response_text, structured_data, usage_info, and additional_thought
    """
    return _get_client().generate_chat(prompt, model, brief, json_schema, context)
