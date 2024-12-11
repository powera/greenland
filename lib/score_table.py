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
    """Get model, benchmark and score data from the database."""
    session = benchmarks.datastore.create_dev_session()

    llms = benchmarks.datastore.list_all_models(session)
    llms.sort(key=lambda x: (x["filesize_mb"], x["displayname"]))

    benchmark_info = benchmarks.datastore.list_all_benchmarks(session)
    for benchmark in benchmark_info:
        benchmark["longname"] = f'{benchmark["codename"]}:{benchmark["metric"]}'

    scores = benchmarks.datastore.get_highest_benchmark_scores(session)
    # Add color information to the data
    for key in scores:
        score = scores[key]
        scores[key] = {
            'value': score,
            'color': get_color(score),
            'run_id': None  # Will be populated with highest scoring run ID
        }

    # Get run IDs for each benchmark-model pair
    for model in llms:
        for benchmark in benchmark_info:
            key = (benchmark["longname"], model["codename"])
            if key in scores:
                highest_run = session.query(benchmarks.datastore.Run).filter_by(
                    model_name=model["codename"],
                    benchmark_name=benchmark["codename"],
                    benchmark_metric=benchmark["metric"]
                ).order_by(benchmarks.datastore.Run.normed_score.desc()).first()
                
                if highest_run:
                    scores[key]['run_id'] = highest_run.run_id

    return {
        "llms": llms,
        "benchmarks": benchmark_info,
        "scores": scores
    }


def generate_dashboard():
    """Generate the main dashboard HTML file."""
    data = get_data()

    # Set up Jinja2 environment
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(current_dir), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('model_scores.html')

    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)

    # Render template and write to file
    output = template.render(data=data)
    with open('output/model_summary.html', 'w') as f:
        f.write(output)


def generate_run_detail(model_name, benchmark_name, benchmark_metric, session=None):
    """
    Generate detailed HTML report for a specific benchmark run.
    
    Args:
        model_name: Name of the model
        benchmark_name: Name of the benchmark
        benchmark_metric: Metric used for the benchmark
        session: Optional SQLAlchemy session (will create if None)
    """
    if not session:
        session = benchmarks.datastore.create_dev_session()

    # Get run details from database
    data = benchmarks.datastore.get_highest_scoring_run_details(
        session, model_name, benchmark_name, benchmark_metric)

    if not data:
        return  # No run details found

    # Set up Jinja2 environment
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(current_dir), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('run_details.html')

    # Render template
    output = template.render(run_details=data)

    # Create run_details directory if it doesn't exist
    os.makedirs('output/run_details', exist_ok=True)

    # Write to file using run_id
    run_id = data['run_id']
    with open(f'output/run_details/{run_id}.html', 'w') as f:
        f.write(output)
