from jinja2 import Environment, FileSystemLoader
import math
import os

import benchmarks.datastore

def get_color(score):
    """
    Convert a score (0-100) to an RGB color value.
    100 = bright green (0, 255, 0)
    Going down to red (255, 0, 0)
    """
    if score == 100:
        return "rgb(0, 255, 0)"
    
    # Convert score to a value between 0 and 1
    normalized = score / 100.0
    
    # Calculate red and green components
    red = int(40 + 215 * (1 - normalized))
    green = int(215 * normalized)
    
    return f"rgb({red}, {green}, 0)"

def get_data():
  session = benchmarks.datastore.create_dev_session()
  llms = benchmarks.datastore.list_all_models(session)
  benchmark_info = benchmarks.datastore.list_all_benchmarks(session)
  scores = benchmarks.datastore.get_highest_benchmark_scores(session)
  return {
      "llms": [x["codename"] for x in llms],
      "benchmarks": [f"""{x["codename"]}:{x["metric"]}""" for x in benchmark_info],
      "scores": scores
      }

# Sample data
data = get_data()

# Set up Jinja2 environment
current_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(os.path.dirname(current_dir), 'templates')

env = Environment(loader=FileSystemLoader(template_dir))
template = env.get_template('model_scores.html')

# Add color information to the data
for key in data['scores']:
    score = data['scores'][key]
    data['scores'][key] = {
        'value': score,
        'color': get_color(score)
    }

# Render template
output = template.render(data=data)

# Write to file
with open('output/model_summary.html', 'w') as f:
    f.write(output)
