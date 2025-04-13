#!/usr/bin/python3

"""Client for interacting with LMStudio API with optional two-phase responses."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Union, Any, List
import requests
from requests.exceptions import Timeout, RequestException

from telemetry import LLMUsage
from clients.types import Response

# Configure logging with DEBUG level option
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER = "192.168.4.77"
PORT = 1234
DEFAULT_MODEL = "lmstudio-community/gemma-3-12b-it-gguf/gemma-3-12b-it-q4_k_m.gguf"  # Responses are good-quality for free generation.
DEFAULT_TIMEOUT = 250

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
    
    def __init__(self, server: str = SERVER, port: int = PORT, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        self.server = server
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{server}:{port}/v1"
        self.debug = debug
        if debug:
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
            
        except Timeout:
            raise LMStudioTimeoutError(f"Request timed out after {self.timeout}s")
        except RequestException as e:
            if e.response is not None:
                error_msg = f"Error {e.response.status_code}: {e.response.text}"
            else:
                error_msg = str(e)
            raise LMStudioRequestError(error_msg) from e

    def _process_chat_response(self, response: requests.Response, model: str) -> tuple[str, LLMUsage]:
        """Process chat response and extract content and usage info."""
        result = ""
        usage = None
        
        try:
            response_data = response.json()
            
            # Extract the message content from the choices array
            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message", {})
                content = message.get("content", "")
                
            # Clean up markdown code blocks if present
            if content.startswith("```"):
                # Remove the first line (```json)
                content_lines = content.split('\n')
                # Remove the first and last lines if they contain backticks
                if content_lines[0].startswith("```"):
                    content_lines = content_lines[1:]
                if content_lines and content_lines[-1].strip() == "```":
                    content_lines = content_lines[:-1]
                content = '\n'.join(content_lines)
            
            result = content
            

            # Extract usage information for telemetry
            if "usage" in response_data:
                usage_data = response_data["usage"]
                # Convert to the format expected by LLMUsage.from_api_response
                converted_usage = {
                    "prompt_tokens": usage_data.get("prompt_tokens", 0),
                    "completion_tokens": usage_data.get("completion_tokens", 0),
                    "total_duration": response.elapsed.total_seconds() * 1000  # Convert to ms
                }
                usage = LLMUsage.from_api_response(converted_usage, model=model)
                
            return result, usage
            
        except ValueError as e:
            # Handle JSON parsing errors
            print(f"Error parsing response: {e}")
            return "", None

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        try:
            response = self._make_request("chat", {"model": model})
            return response.status_code == 200
        except LMStudioError:
            return False

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Response:
        raise Exception("Not supported.")

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
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
            logger.debug("Chat request: model=%s, brief=%s, schema=%s", 
                        model, brief, bool(json_schema))
        
        # Phase 1: Get response (either free-form or JSON)
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
            
        if json_schema:
            # Add schema to prompt for single-phase JSON response
            schema_prompt = f"""Provide a JSON response matching this schema:
{json.dumps(json_schema, indent=2)}

Query: {prompt}"""
            messages.append({"role": "user", "content": schema_prompt})
        else:
            messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        
        if brief:
            data["options"] = {"num_predict": 256}

        if json_schema:
            data["format"] = json_schema
            
        response = self._make_request("chat/completions", data)
        response_text, response_usage = self._process_chat_response(response, model)
        print(response_text)
        # Handle JSON responses
        if json_schema:
            # Single-phase JSON response
            try:
                structured_response = json.loads(response_text)
                return Response(
                    response_text="",
                    structured_data=structured_response,
                    usage=response_usage
                )
            except json.JSONDecodeError:
                return Response(
                    response_text="",
                    structured_data={"error": f"Failed to parse JSON: {response_text}"},
                    usage=response_usage
                )
        else:
            # Text-only response
            return Response(
                response_text=response_text,
                structured_data={},
                usage=response_usage
            )

# Create default client instance
client = LMStudioClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str = DEFAULT_MODEL) -> Response:
    return client.generate_text(prompt, model)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Response:
    """
    Generate a chat response.
    
    Returns:
        Response data class containing response_text, structured_data, and usage_info
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)
