#!/usr/bin/python3

"""Client for interacting with Ollama API."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union, Any
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

class OllamaClient:
    """Client for making requests to Ollama API."""
    
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
        structured_json: bool = False,
        json_schema: Optional[Dict] = None
    ) -> Tuple[str, UsageInfo]:
        """Generate chat completion using Ollama API."""
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        
        if brief:
            data["options"] = {"num_predict": 256}
        if structured_json:
            data["format"] = "json"
        if json_schema:
            data["format"] = json_schema
            
        response = self._make_request("chat", data)
        result = ""
        usage = None
        
        for line in response.iter_lines():
            if line:
                response_data = json.loads(line.decode('utf-8'))
                if "total_duration" in response_data:
                    usage = UsageInfo.from_response(response_data)
                if "message" in response_data:
                    result += response_data["message"]["content"]
                    
        logger.debug("Response: %s", result)
        return result, usage

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
    structured_json: bool = False,
    json_schema: Optional[Dict] = None
) -> Tuple[str, Dict]:
    result, usage = client.generate_chat(prompt, model, brief, structured_json, json_schema)
    return result, vars(usage)
