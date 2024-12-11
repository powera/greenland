import requests
import json

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER = "100.123.16.86"


def warm_model(model):
  url = f"http://{SERVER}:11434/api/chat"
  data = {
      "model": model,
      "messages": []
  }
  response = requests.post(url, json=data, timeout=50)
  return response.status_code == 200


def generate_text(prompt, model="smollm:360m"):
  url = f"http://{SERVER}:11434/api/generate"
  
  data = {
      "model": model,
      "prompt": prompt,
      "stream": False,
  }
  
  response = requests.post(url, json=data, timeout=50)
  
  if response.status_code == 200:
    result = ""
    for line in response.iter_lines():
      if line:
        decoded_line = line.decode('utf-8')
        response_data = json.loads(decoded_line)
        if "total_duration" in response_data:
          usage = parse_usage(response_data)
        result += response_data.get('response', '')
    return result, usage
  else:
    raise Exception(f"Error: {response.status_code} - {response.text}")


def generate_chat(
    prompt, model="smollm:360m", brief=False,
    structured_json=False, json_schema=None):
  url = f"http://{SERVER}:11434/api/chat"
  
  data = {
      "model": model,
      "messages": [
        { "role": "user",
          "content": prompt, }
        ],
      "stream": False,
  }
  if brief:
    data["options"] = {}
    data["options"]["num_predict"] = 256
  if structured_json:
    data["format"] = "json"
  if json_schema:  # Overrides json schema
    data["format"] = json_schema
  
  response = requests.post(url, json=data, timeout=50)
  if response.status_code == 200:
    result = ""
    usage = ""
    for line in response.iter_lines():
      if line:
        decoded_line = line.decode('utf-8')
        response_data = json.loads(decoded_line)
        if "total_duration" in response_data:
          usage = parse_usage(response_data)
        if "message" in response_data:
          result += response_data["message"]["content"]
    print(result)
    return result, usage
  else:
    raise Exception(f"Error: {response.status_code} - {response.text}")


def parse_usage(response_data):
  usage = {"tokens_in": response_data.get("prompt_eval_count"), "tokens_out": response_data.get("eval_count"), "cost": estimate_cost(response_data), "total_msec": response_data.get("total_duration") / 1_000_000}
  logger.debug(f"Model: {response_data.get('model', 'N/A')}")
  logger.debug(f"Total duration: {response_data.get('total_duration', 'N/A')}")
  logger.debug(f"Load duration: {response_data.get('load_duration', 'N/A')}")
  logger.debug(f"Prompt eval duration: {response_data.get('prompt_eval_duration', 'N/A')}")
  logger.debug(f"Eval duration: {response_data.get('eval_duration', 'N/A')}")
  return usage


def estimate_cost(response_data):
  # We use an estimate of $0.01 per 1000 seconds for the cost of running a local model
  duration = response_data.get('total_duration') / (1000*1000*1000)
  return duration * (0.01 / 1000)
