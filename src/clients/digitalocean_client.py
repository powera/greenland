#!/usr/bin/python3
"""Client for DigitalOcean Gradient serverless inference (OpenAI Chat Completions).

DigitalOcean fronts models from several vendors behind one OpenAI-compatible
``/chat/completions`` endpoint and one ``sk-do-…`` key. Model ids are flat,
provider-embedded strings (``anthropic-claude-fable-5``, ``openai-gpt-5.6-sol``,
``llama-4-maverick``), which is why the router selects this backend by an
explicit ``do/`` prefix rather than by sniffing the model name.

This is a separate module rather than a variant of ``clients.openai.client``:
that client speaks the Responses API, and keeping the two dialects apart makes
a future consolidation a deletion rather than an untangling.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

import clients.lib
from clients.keys import load_key
from clients.types import Response
from util.telemetry import LLMUsage

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

API_BASE = "https://inference.do-ai.run/v1"
DEFAULT_MODEL = "openai-gpt-5.6-sol"
DEFAULT_TIMEOUT = 120

# Several DO-hosted open models emit chain-of-thought inside <think> tags in the
# ordinary content field; it is split out into Response.additional_thought rather
# than left to corrupt the answer (or the JSON).
_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)


class DigitalOceanClient:
    """Client for making direct HTTP requests to DigitalOcean Gradient inference."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        debug: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize the DigitalOcean client.

        Args:
            timeout: Request timeout in seconds.
            debug: Whether to enable debug logging.
            api_key: Optional API key to use instead of loading from
                ``keys/digitalocean.key``. Useful for API server use where keys
                come from request parameters.
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized DigitalOceanClient in debug mode")

        self.api_key = api_key if api_key else load_key("digitalocean", required=False)
        if self.api_key:
            self.headers: Dict[str, str] = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}

    def _create_completion(self, **kwargs: Any) -> Tuple[Dict[str, Any], float]:
        """POST to the DigitalOcean chat/completions endpoint.

        Returns:
            Tuple of (decoded JSON body, request duration in milliseconds).
        """
        clients.lib.assert_llm_calls_enabled("digitalocean")

        url = f"{API_BASE}/chat/completions"

        if self.debug:
            logger.debug("Making request to %s", url)
            logger.debug("Request data: %s", json.dumps(kwargs, indent=2))

        start_time = time.time()
        response = requests.post(url, headers=self.headers, json=kwargs, timeout=self.timeout)
        duration_ms = (time.time() - start_time) * 1000

        if response.status_code != 200:
            error_msg = f"Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        result: Dict[str, Any] = response.json()
        return result, duration_ms

    def warm_model(self, model: str) -> bool:
        """No-op warmup; DigitalOcean serves models on demand."""
        if self.debug:
            logger.debug("Model warmup not required for DigitalOcean: %s", model)
        return True

    def _build_messages(
        self,
        prompt: str,
        context: Optional[str],
        messages: Optional[List[clients.lib.ChatMessage]],
    ) -> List[Dict[str, str]]:
        """Build the Chat Completions ``messages`` array.

        Chat Completions tolerates consecutive same-role messages, so a
        caller-supplied conversation passes through unmodified (no
        ``normalize_alternating_messages`` as Anthropic/Gemini require).
        """
        built: List[Dict[str, str]] = []
        if context:
            built.append({"role": "system", "content": context})
        if messages:
            for message in messages:
                built.append({"role": message["role"], "content": message["content"]})
        else:
            built.append({"role": "user", "content": prompt})
        return built

    def _split_thinking(self, content: str) -> Tuple[str, Optional[str]]:
        """Strip ``<think>…</think>`` blocks out of content into a thought string."""
        additional_thought: Optional[str] = None
        match = _THINK_PATTERN.search(content)
        while match:
            thought = match.group(1).strip()
            if additional_thought is None:
                additional_thought = thought
            else:
                additional_thought += " " + thought
            content = content.replace(f"<think>{match.group(1)}</think>", "")
            match = _THINK_PATTERN.search(content)
        return content, additional_thought

    def _strip_code_fence(self, content: str) -> str:
        """Remove a wrapping markdown code fence, which several models add."""
        if not content.startswith("```"):
            return content
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
        messages: Optional[List[clients.lib.ChatMessage]] = None,
        max_tokens: Optional[int] = None,
    ) -> Response:
        """Generate a chat response via DigitalOcean Gradient inference.

        Args:
            prompt: The main prompt/question (ignored if ``messages`` is given).
            model: DigitalOcean model id, with the router's ``do/`` prefix
                already stripped (e.g. ``anthropic-claude-fable-5``).
            brief: Whether to limit response length.
            json_schema: Schema for structured response, either a
                ``clients.types.Schema`` or a plain JSON-schema dict.
            context: Optional system message prepended to the conversation.
            messages: Optional provider-neutral message list, passed through
                as the Chat Completions ``messages`` array.
            max_tokens: Explicit output-token limit, normally from
                ``clients.lib.limit_from_estimate()``.

        Returns:
            Response containing response_text, structured_data, and usage.

        Raises:
            RuntimeError: If the API key is unavailable or the request fails.
            clients.lib.TruncatedResponseError: If generation stopped at the limit.
            ValueError: If a schema was requested and the reply is not valid JSON.
        """
        if not self.api_key:
            raise RuntimeError(
                "DigitalOcean API key not available. Please ensure keys/digitalocean.key exists."
            )

        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("JSON schema: %s", json_schema)

        token_limit = clients.lib.resolve_output_tokens(
            model, brief=brief, requested=max_tokens, backend_default=4096
        )

        request_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(prompt, context, messages),
            "max_tokens": token_limit,
            "stream": False,
        }

        if json_schema:
            if isinstance(json_schema, clients.lib.Schema):
                schema_obj = json_schema
            else:
                schema_obj = clients.lib.schema_from_dict(json_schema)

            clean_schema = clients.lib.to_openai_schema(schema_obj)
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "Details",
                    "strict": True,
                    "schema": clean_schema,
                },
            }

        response_data, duration_ms = self._create_completion(**request_kwargs)

        choices = response_data.get("choices") or []
        content = ""
        finish_reason: Optional[str] = None
        if choices:
            first_choice = choices[0]
            message = first_choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = first_choice.get("finish_reason")

        content, additional_thought = self._split_thinking(content)
        content = self._strip_code_fence(content)

        usage_data = response_data.get("usage") or {}
        completion_tokens = usage_data.get("completion_tokens", 0)
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": completion_tokens,
                "total_duration": duration_ms,
            },
            model=model,
        )

        # Did generation stop because it ran out of room? finish_reason names the
        # reason when the provider sets it, but spending the whole budget is the
        # signal that needs no cooperation: a response that ended on its own terms
        # stops short of the cap.
        hit_token_limit = isinstance(completion_tokens, int) and completion_tokens >= token_limit
        if finish_reason == "length" or hit_token_limit:
            raise clients.lib.TruncatedResponseError(
                f"DigitalOcean stopped generating at the {token_limit}-token output limit "
                f"(model={model}, completion_tokens={completion_tokens}, "
                f"finish_reason={finish_reason!r}). Raise the limit or split the request."
            )

        if json_schema:
            try:
                structured_data = json.loads(content)
            except json.JSONDecodeError as exc:
                # Do not return {"error": ...}: structured_data is merged into the
                # caller's result dict, so an error payload reads as a successful
                # response with odd keys.
                raise ValueError(
                    f"Failed to parse JSON response from {model}: {content!r}"
                ) from exc
            response_text = ""
        else:
            structured_data = {}
            response_text = content

        if self.debug:
            logger.debug("Response text: %s", response_text)
            logger.debug("Structured data: %s", structured_data)
            logger.debug("Usage metrics: %s", usage.to_dict())

        return Response(
            response_text=response_text,
            structured_data=structured_data,
            usage=usage,
            additional_thought=additional_thought,
        )


# Lazy client instance - only created when first accessed
_client: Optional[DigitalOceanClient] = None


def _get_client() -> DigitalOceanClient:
    """Get or create the default client instance."""
    global _client
    if _client is None:
        _client = DigitalOceanClient(debug=False)
    return _client


# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return _get_client().warm_model(model)


def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Any] = None,
    context: Optional[str] = None,
) -> Response:
    """Generate a chat response using DigitalOcean Gradient inference."""
    return _get_client().generate_chat(prompt, model, brief, json_schema, context)
