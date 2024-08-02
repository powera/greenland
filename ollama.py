import requests
import json

SERVER = "100.123.16.86"

def generate_text(prompt, model="phi3:3.8b"):
  url = f"http://{SERVER}:11434/api/generate"
  
  data = {
      "model": model,
      "prompt": prompt
  }
  
  response = requests.post(url, json=data)
  
  if response.status_code == 200:
    result = ""
    for line in response.iter_lines():
      if line:
        decoded_line = line.decode('utf-8')
        response_data = json.loads(decoded_line)
        result += response_data.get('response', '')
    return result
  else:
    return f"Error: {response.status_code} - {response.text}"
