#!/usr/bin/python3

"""Client for interacting with LMStudio API with optional two-phase responses."""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

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
MODEL_READY_POLL_TIMEOUT = 600
MODEL_READY_POLL_INTERVAL = 2.0


class LMStudioError(Exception):
    """Base exception for LMStudio client errors."""

    pass


class LMStudioTimeoutError(LMStudioError):
    """Raised when an LMStudio request times out."""

    pass


class LMStudioRequestError(LMStudioError):
    """Raised when an LMStudio request fails."""

    pass


class LMStudioModelMismatchError(LMStudioError):
    """Raised when LMStudio responds with a model different from the requested model."""

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

        if endpoint == "chat/completions" and "model" not in data:
            raise LMStudioRequestError("LMStudio chat/completions request missing required 'model'")

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
        self,
        response: requests.Response,
        model: str,
        expected_response_model: Optional[str] = None,
    ) -> tuple[str, Optional[LLMUsage], Optional[str]]:
        """Process chat response and extract content, usage info, and additional thoughts."""
        result = ""
        usage: Optional[LLMUsage] = None
        additional_thought = None

        # Pattern to extract content within <think> tags
        think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)

        try:
            response_data = response.json()
            response_model = response_data.get("model")
            if not isinstance(response_model, str) or not response_model:
                raise LMStudioModelMismatchError(
                    "LMStudio response did not include a valid model identifier"
                )

            expected_model = expected_response_model or model
            if not self._models_match(
                requested_model=expected_model, response_model=response_model
            ):
                raise LMStudioModelMismatchError(
                    "LMStudio response model mismatch: "
                    f"requested '{expected_model}' but response used '{response_model}'"
                )

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

    def _normalize_model_name_for_compare(self, model_name: str) -> str:
        normalized_name = model_name.strip().lower()
        if normalized_name.startswith("lmstudio/"):
            normalized_name = normalized_name[len("lmstudio/") :]
        return normalized_name

    def _models_match(self, requested_model: str, response_model: str) -> bool:
        normalized_requested_model = self._normalize_model_name_for_compare(requested_model)
        normalized_response_model = self._normalize_model_name_for_compare(response_model)
        return normalized_requested_model == normalized_response_model

    def warm_model(self, model: str, load_name: Optional[str] = None) -> bool:
        """Ensure model is the only loaded model and wait until it is ready.

        If the model is already loaded and ready, returns True immediately.
        Any other loaded models are unloaded first to avoid multiple copies
        consuming memory simultaneously.

        Args:
            model: Model identifier used for state polling (matched against /api/v0/models id).
            load_name: Model identifier to send in the load POST body.  Defaults to model.
                       Should be the bare id returned by LM Studio (e.g. "qwen3-4b"), not
                       the full GGUF path, so the load API accepts it.
        """
        effective_load_name = load_name or model

        # Fast path: already loaded/idle.
        state = self._get_model_state(model)
        if state in ("loaded", "idle"):
            logger.info("Model %s is already loaded and ready.", model)
            return True

        # Unload any other loaded models before loading the target.
        for other_id in self._get_loaded_model_ids():
            if not self._id_matches_model(other_id, model):
                logger.info("Unloading model %s before loading %s.", other_id, model)
                self.unload_model(other_id)

        # Send load POST (may block or time out — that's OK).
        self._send_load_request(effective_load_name)

        # Poll until loaded or timeout.
        deadline = time.time() + MODEL_READY_POLL_TIMEOUT
        while time.time() < deadline:
            poll_state = self._get_model_state(model)
            if poll_state in ("loaded", "idle"):
                return True
            if poll_state == "not-loaded":
                # Not loading at all — retry the load request.
                self._send_load_request(effective_load_name)
            time.sleep(MODEL_READY_POLL_INTERVAL)

        logger.warning("Model %s did not become ready within %ss", model, MODEL_READY_POLL_TIMEOUT)
        return False

    def _get_model_state(self, model: str) -> Optional[str]:
        """Return the state string for model from /api/v0/models, or None if unreachable/not found.

        State values: "loading", "not-loaded", "loaded", "idle".
        Matches by exact id or by the last path component (e.g. "gemma-2-2b-it"
        matches "google/gemma-2-2b-it").
        """
        url = f"http://{self.server}:{self.port}/api/v0/models"
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)
        try:
            response = requests.get(url, timeout=operation_timeout)
            if not response.ok:
                return None
            entries = response.json().get("data", [])
            if not isinstance(entries, list):
                return None
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id")
                if not isinstance(entry_id, str):
                    continue
                if self._id_matches_model(entry_id, model):
                    state = entry.get("state")
                    return state if isinstance(state, str) else None
            return None
        except (RequestException, ValueError):
            return None

    def _get_loaded_model_ids(self) -> List[str]:
        """Return ids of all models that are not in state "not-loaded" per /api/v0/models."""
        url = f"http://{self.server}:{self.port}/api/v0/models"
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)
        try:
            response = requests.get(url, timeout=operation_timeout)
            if not response.ok:
                return []
            entries = response.json().get("data", [])
            if not isinstance(entries, list):
                return []
            result: List[str] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("state") == "not-loaded":
                    continue
                entry_id = entry.get("id")
                if isinstance(entry_id, str) and entry_id:
                    result.append(entry_id)
            return result
        except (RequestException, ValueError):
            return []

    def _id_matches_model(self, entry_id: str, model: str) -> bool:
        """Return True if the /api/v0/models id matches the caller-supplied model name."""
        return entry_id == model or model.endswith("/" + entry_id)

    def _send_load_request(self, model: str) -> None:
        """Send a load POST for model; ignore errors (caller polls for readiness)."""
        url = f"http://{self.server}:{self.port}/api/v1/models/load"
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)
        try:
            if self.debug:
                logger.debug("Load POST for model %s", model)
            requests.post(url, json={"model": model}, timeout=operation_timeout)
        except (ConnectTimeout, ReadTimeout, RequestException) as exc:
            if self.debug:
                logger.debug("Load POST for %s failed: %s", model, exc)

    def unload_model(self, model: str) -> bool:
        """Unload model from memory using LM Studio's model unload endpoint."""
        url = f"http://{self.server}:{self.port}/api/v1/models/unload"
        operation_timeout = min(self.timeout, MODEL_OPERATION_TIMEOUT)
        try:
            response = requests.post(url, json={"instance_id": model}, timeout=operation_timeout)
            if response.ok:
                return True
            response_text = response.text.lower()
            return "not loaded" in response_text or "already unloaded" in response_text
        except (ConnectTimeout, ReadTimeout, RequestException):
            return False

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
        expected_response_model: Optional[str] = None,
    ) -> Response:
        """
        Generate chat completion using LMStudio API.

        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt
            expected_response_model: Optional model name expected in LM Studio response

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

        if not model:
            raise LMStudioRequestError("LMStudio generate_chat requires a non-empty model")

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
            response, model, expected_response_model=expected_response_model
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
    expected_response_model: Optional[str] = None,
) -> Response:
    """
    Generate a chat response.

    Returns:
        Response data class containing response_text, structured_data, usage_info, and additional_thought
    """
    return _get_client().generate_chat(
        prompt,
        model,
        brief,
        json_schema,
        context,
        expected_response_model=expected_response_model,
    )
