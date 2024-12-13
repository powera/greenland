#!/usr/bin/python3

"""Client for interacting with Ollama API with two-phase responses."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union, Any, List
import requests

# Configure logging with DEBUG level option
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER = "100.123.16.86"
DEFAULT_MODEL = "smollm2:360m"  # Responses are low-quality but generally coherent.
DEFAULT_TIMEOUT = 50

@dataclass
class UsageInfo:
    """Tracks token usage and cost information."""
    tokens_in: int
    tokens_out: int
    total_msec: float
    cost: float

    @classmethod
    def from_response(cls, response_data: Dict[str, Any]) -> 'UsageInfo':
        """Create UsageInfo from Ollama response data."""
        duration = response_data.get('total_duration', 0) / 1_000_000  # Convert to ms
        return cls(
            tokens_in=response_data.get('prompt_eval_count', 0),
            tokens_out=response_data.get('eval_count', 0),
            total_msec=duration,
            cost=duration * (0.01 / 1000000)  # $0.01 per 1000 seconds
        )

    def combine(self, other: 'UsageInfo') -> 'UsageInfo':
        """Combine usage information from multiple responses."""
        return UsageInfo(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            total_msec=self.total_msec + other.total_msec,
            cost=self.cost + other.cost
        )

@dataclass
class TwoPhaseResponse:
    """Container for both free-form and structured responses."""
    free_response: str
    structured_response: Dict[str, Any]
    usage: UsageInfo

class OllamaClient:
    """Client for making requests to Ollama API with two-phase responses."""
    
    def __init__(self, server: str = SERVER, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        self.server = server
        self.timeout = timeout
        self.base_url = f"http://{server}:11434/api"
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OllamaClient in debug mode")

    def _make_request(self, endpoint: str, data: Dict) -> requests.Response:
        """Make HTTP request to Ollama API."""
        url = f"{self.base_url}/{endpoint}"
        
        if self.debug:
            logger.debug("Making request to %s", url)
            logger.debug("Request data: %s", json.dumps(data, indent=2))
            
        response = requests.post(url, json=data, timeout=self.timeout)
        
        if self.debug:
            logger.debug("Response status code: %d", response.status_code)
            
        if response.status_code != 200:
            error_msg = f"Error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        return response

    def _process_chat_response(self, response: requests.Response) -> Tuple[str, UsageInfo]:
        """Process chat response and extract content and usage info."""
        result = ""
        usage = None
        
        if self.debug:
            logger.debug("Processing chat response...")
            
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode('utf-8'))
                if self.debug:
                    logger.debug("Response data: %s", json.dumps(response_data, indent=2))
                    
                if "total_duration" in response_data:
                    usage = UsageInfo.from_response(response_data)
                    if self.debug:
                        logger.debug("Usage info: %s", vars(usage))
                        
                if "message" in response_data:
                    result += response_data["message"]["content"]
                    
        return result, usage

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        if self.debug:
            logger.debug("Warming up model: %s", model)
            
        response = self._make_request("chat", {"model": model, "messages": []})
        success = response.status_code == 200
        
        if self.debug:
            logger.debug("Model warmup %s", "successful" if success else "failed")
            
        return success

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, UsageInfo]:
        """Generate text completion using Ollama API."""
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)
            
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
                    usage = UsageInfo.from_response(response_data)
                result += response_data.get('response', '')
                
        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage info: %s", vars(usage))
                
        return result, usage

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> TwoPhaseResponse:
        """
        Generate two-phase chat completion using Ollama API.
        
        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt
        
        Returns:
            TwoPhaseResponse containing both free-form and structured responses
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json.dumps(json_schema, indent=2) if json_schema else None)
        
        # Phase 1: Get free-form response
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        
        if self.debug:
            logger.debug("Phase 1 messages: %s", json.dumps(messages, indent=2))
        
        data = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        
        if brief:
            data["options"] = {"num_predict": 256}
            
        response = self._make_request("chat", data)
        free_response, free_usage = self._process_chat_response(response)
        
        if self.debug:
            logger.debug("Phase 1 response: %s", free_response)
            logger.debug("Phase 1 usage: %s", vars(free_usage))
        
        # Phase 2: Get structured response
        if json_schema:
            structure_prompt = f"""Based on the previous response to the prompt:
{prompt}

Provide a structured response following this schema:
{json.dumps(json_schema, indent=2)}"""
            
            if self.debug:
                logger.debug("Phase 2 structure prompt: %s", structure_prompt)
            
            data = {
                "model": model,
                "messages": messages + [
                    {"role": "assistant", "content": free_response},
                    {"role": "user", "content": structure_prompt}
                ],
                "format": json_schema,
                "stream": False,
            }
            
            response = self._make_request("chat", data)
            json_response, json_usage = self._process_chat_response(response)
            
            if self.debug:
                logger.debug("Phase 2 JSON response: %s", json_response)
                logger.debug("Phase 2 usage: %s", vars(json_usage))
            
            try:
                structured_response = json.loads(json_response)
            except json.JSONDecodeError:
                error_msg = f"Failed to parse JSON response: {json_response}"
                logger.error(error_msg)
                structured_response = {"error": error_msg}
        else:
            structured_response = {}
            json_usage = UsageInfo(0, 0, 0, 0)
        
        # Combine usage from both phases
        total_usage = free_usage.combine(json_usage)
        
        if self.debug:
            logger.debug("Total usage: %s", vars(total_usage))
        
        return TwoPhaseResponse(
            free_response=free_response,
            structured_response=structured_response,
            usage=total_usage
        )

# Create default client instance
client = OllamaClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, Dict]:
    result, usage = client.generate_text(prompt, model)
    return result, vars(usage)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Tuple[str, Dict[str, Any], Dict]:
    """
    Generate a two-phase chat response.
    
    Returns:
        Tuple containing (free_response, structured_response, usage_info)
    """
    response = client.generate_chat(prompt, model, brief, json_schema, context)
    return response.free_response, response.structured_response, vars(response.usage)
