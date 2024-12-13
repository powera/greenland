#!/usr/bin/python3

"""Client for interacting with Ollama API with two-phase responses."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union, Any, List
import requests

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
    
    def __init__(self, server: str = SERVER, timeout: int = DEFAULT_TIMEOUT):
        self.server = server
        self.timeout = timeout
        self.base_url = f"http://{server}:11434/api"

    def _make_request(self, endpoint: str, data: Dict) -> requests.Response:
        """Make HTTP request to Ollama API."""
        url = f"{self.base_url}/{endpoint}"
        response = requests.post(url, json=data, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return response

    def _process_chat_response(self, response: requests.Response) -> Tuple[str, UsageInfo]:
        """Process chat response and extract content and usage info."""
        result = ""
        usage = None
        
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode('utf-8'))
                if "total_duration" in response_data:
                    usage = UsageInfo.from_response(response_data)
                if "message" in response_data:
                    result += response_data["message"]["content"]
                    
        return result, usage

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        response = self._make_request("chat", {"model": model, "messages": []})
        return response.status_code == 200

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, UsageInfo]:
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
                    usage = UsageInfo.from_response(response_data)
                result += response_data.get('response', '')
                
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
        # Phase 1: Get free-form response
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        
        if brief:
            data["options"] = {"num_predict": 256}
            
        response = self._make_request("chat", data)
        free_response, free_usage = self._process_chat_response(response)
        
        # Phase 2: Get structured response
        if json_schema:
            structure_prompt = f"""Based on the previous response to the prompt:
{prompt}

Provide a structured response following this schema:
{json.dumps(json_schema, indent=2)}"""
            
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
            
            try:
                structured_response = json.loads(json_response)
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response: %s", json_response)
                structured_response = {"error": "Failed to generate valid JSON response"}
        else:
            structured_response = {}
            json_usage = UsageInfo(0, 0, 0, 0)
        
        # Combine usage from both phases
        total_usage = free_usage.combine(json_usage)
        
        return TwoPhaseResponse(
            free_response=free_response,
            structured_response=structured_response,
            usage=total_usage
        )

# Create default client instance
client = OllamaClient()

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
