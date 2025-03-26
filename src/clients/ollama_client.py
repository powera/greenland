#!/usr/bin/python3

"""Client for interacting with Ollama API with optional two-phase responses."""

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

SERVER = "100.123.16.86"
DEFAULT_MODEL = "smollm2:360m"  # Responses are low-quality but generally coherent.
DEFAULT_TIMEOUT = 50

class OllamaError(Exception):
    """Base exception for Ollama client errors."""
    pass

class OllamaTimeoutError(OllamaError):
    """Raised when an Ollama request times out."""
    pass

class OllamaRequestError(OllamaError):
    """Raised when an Ollama request fails."""
    pass

class OllamaClient:
    """Client for making requests to Ollama API with optional two-phase responses."""
    
    def __init__(self, server: str = SERVER, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        self.server = server
        self.timeout = timeout
        self.base_url = f"http://{server}:11434/api"
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

    def _make_request(self, endpoint: str, data: Dict) -> requests.Response:
        """Make HTTP request to Ollama API."""
        url = f"{self.base_url}/{endpoint}"
        
        if self.debug:
            logger.debug("Request to %s: %s", url, json.dumps(data, indent=2))
            
        try:
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response
            
        except Timeout:
            raise OllamaTimeoutError(f"Request timed out after {self.timeout}s")
        except RequestException as e:
            if e.response is not None:
                error_msg = f"Error {e.response.status_code}: {e.response.text}"
            else:
                error_msg = str(e)
            raise OllamaRequestError(error_msg) from e

    def _process_chat_response(self, response: requests.Response, model: str) -> tuple[str, LLMUsage]:
        """Process chat response and extract content and usage info."""
        result = ""
        usage = None
            
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode('utf-8'))
                    
                if "total_duration" in response_data:
                    usage = LLMUsage.from_api_response(response_data, model=model)
                        
                if "message" in response_data:
                    result += response_data["message"]["content"]
                    
        return result, usage

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        try:
            response = self._make_request("chat", {"model": model, "messages": []})
            return response.status_code == 200
        except OllamaError:
            return False

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Response:
        """Generate text completion using Ollama API."""
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        
        response = self._make_request("generate", data)
        result = ""
        usage = None
        
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode('utf-8'))
                if "total_duration" in response_data:
                    usage = LLMUsage.from_api_response(response_data, model=model)
                result += response_data.get('response', '')
                
        if self.debug:
            logger.debug("Generated %d characters", len(result))
                
        return Response(
            response_text=result,
            structured_data={},
            usage=usage
        )

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> Response:
        """
        Generate chat completion using Ollama API.
        
        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt
        
        Returns:
            Response data class
            
        Raises:
            OllamaTimeoutError: If request times out
            OllamaRequestError: If request fails
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
            
        response = self._make_request("chat", data)
        response_text, response_usage = self._process_chat_response(response, model)
        
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
client = OllamaClient(debug=False)  # Set to True to enable debug logging

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
    context: Optional[str] = None,
    two_phase: bool = True
) -> Response:
    """
    Generate a chat response.
    
    Returns:
        Response data class containing response_text, structured_data, and usage_info
    """
    return client.generate_chat(prompt, model, brief, json_schema, context, two_phase)
