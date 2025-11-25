#!/usr/bin/python3

"""Client for interacting with Ollama API with optional two-phase responses."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Union, Any, List
import requests
from requests.exceptions import Timeout, RequestException

from telemetry import LLMUsage
from clients.types import Response
import clients.lib

# Configure logging with DEBUG level option
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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

    def _process_chat_response(self, response: requests.Response, model: str) -> tuple[str, LLMUsage, Optional[str]]:
        """Process chat response and extract content, usage info, and additional thoughts."""
        result = ""
        usage = None
        additional_thought = None
        
        # Pattern to extract content within <think> tags
        think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)
            
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode("utf-8"))
                    
                if "total_duration" in response_data:
                    usage = LLMUsage.from_api_response(response_data, model=model)
                        
                if "message" in response_data:
                    content = response_data["message"]["content"]
                    
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
                    
                    result += content
                    
        return result, usage, additional_thought

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        try:
            response = self._make_request("chat", {"model": model})
            return response.status_code == 200
        except OllamaError:
            return False

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Any] = None,
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
            if isinstance(json_schema, clients.lib.Schema):
                schema_obj = json_schema
            else:
                schema_obj = clients.lib.schema_from_dict(json_schema)
            
            clean_schema = clients.lib.to_ollama_schema(schema_obj)

            # Add schema explanation to system prompt for better results
            # Create a clean version of the schema for display, omitting unnecessary implementation details
            display_schema = {
                "type": "object",
                "properties": clean_schema.get("properties", {}),
                "required": clean_schema.get("required", [])
            }
            
            schema_prompt = f"""Please provide a response that matches exactly this schema:
{json.dumps(display_schema, indent=2)}

Your response must be valid JSON that follows the above schema."""

            messages.append({"role": "user", "content": prompt})
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
            data["format"] = clean_schema
            
        response = self._make_request("chat", data)
        response_text, response_usage, additional_thought = self._process_chat_response(response, model)
        if self.debug and additional_thought:
            print("Thought process:", additional_thought)
            
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
                    additional_thought=additional_thought
                )
            except json.JSONDecodeError:
                return Response(
                    response_text="",
                    structured_data={"error": f"Failed to parse JSON: {response_text}"},
                    usage=response_usage,
                    additional_thought=additional_thought
                )
        else:
            # Text-only response
            if self.debug:
                print(response_text)
            return Response(
                response_text=response_text,
                structured_data={},
                usage=response_usage,
                additional_thought=additional_thought
            )

# Create default client instance
client = OllamaClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Any] = None,
    context: Optional[str] = None
) -> Response:
    """
    Generate a chat response.
    
    Returns:
        Response data class containing response_text, structured_data, usage_info, and additional_thought
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)