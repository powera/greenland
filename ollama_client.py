import requests
import json

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER = "100.123.16.86"

def generate_text(prompt, model="phi3:3.8b"):
  url = f"http://{SERVER}:11434/api/generate"
  
  data = {
      "model": model,
      "prompt": prompt,
      "stream": False,
  }
  
  response = requests.post(url, json=data)
  
  if response.status_code == 200:
    result = ""
    for line in response.iter_lines():
      if line:
        decoded_line = line.decode('utf-8')
        response_data = json.loads(decoded_line)
        if "total_duration" in response_data:
          logger.info(f"Model: {response_data.get('model', 'N/A')}")
          logger.info(f"Created at: {response_data.get('created_at', 'N/A')}")
          logger.info(f"Total duration: {response_data.get('total_duration', 'N/A')}")
          logger.info(f"Load duration: {response_data.get('load_duration', 'N/A')}")
          logger.info(f"Prompt eval count: {response_data.get('prompt_eval_count', 'N/A')}")
          logger.info(f"Prompt eval duration: {response_data.get('prompt_eval_duration', 'N/A')}")
          logger.info(f"Eval count: {response_data.get('eval_count', 'N/A')}")
          logger.info(f"Eval duration: {response_data.get('eval_duration', 'N/A')}")
        result += response_data.get('response', '')
    return result
  else:
    return f"Error: {response.status_code} - {response.text}"
