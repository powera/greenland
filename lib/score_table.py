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
  llms.sort(key=lambda x: (x["filesize_mb"], x["displayname"]))
  for key in llms:
    key["dirname"] = key["codename"].replace(":", "__")

  benchmark_info = benchmarks.datastore.list_all_benchmarks(session)
  for key in benchmark_info:
    key["longname"] = f'{key["codename"]}:{key["metric"]}'

  scores = benchmarks.datastore.get_highest_benchmark_scores(session)
  # Add color information to the data
  for key in scores:
      score = scores[key]
      scores[key] = {
          'value': score,
          'color': get_color(score)
      }

  return {
      "llms": llms,
      "benchmarks": benchmark_info,
      "scores": scores
      }

def generate_dashboard():
  data = get_data()

  # Set up Jinja2 environment
  current_dir = os.path.dirname(os.path.abspath(__file__))
  template_dir = os.path.join(os.path.dirname(current_dir), 'templates')

  env = Environment(loader=FileSystemLoader(template_dir))
  template = env.get_template('model_scores.html')

  # Render template
  output = template.render(data=data)

  # Write to file
  with open('output/model_summary.html', 'w') as f:
      f.write(output)


def generate_run_detail(model_name, benchmark_name, benchmark_metric):
  session = benchmarks.datastore.create_dev_session()
  data = benchmarks.datastore.get_highest_scoring_run_details(
      session, model_name, benchmark_name, benchmark_metric)

  # Set up Jinja2 environment
  current_dir = os.path.dirname(os.path.abspath(__file__))
  template_dir = os.path.join(os.path.dirname(current_dir), 'templates')

  env = Environment(loader=FileSystemLoader(template_dir))
  template = env.get_template('run_details.html')

  # Render template
  output = template.render(run_details=data)

  # Write to file
  dirname = f'output/{model_name}'.replace(":", "__")
  try:
    os.mkdir(dirname)
  except FileExistsError:
    pass
  with open(f'{dirname}/{benchmark_name}__{benchmark_metric}.html', 'w') as f:
      f.write(output)
