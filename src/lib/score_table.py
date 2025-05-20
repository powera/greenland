#!/usr/bin/python3
"""Generates HTML score tables and detailed reports for benchmark results."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader
import logging

import datastore.benchmarks
import datastore.common
import constants

@dataclass
class ScoreData:
    """Represents score data for a benchmark run."""
    value: int
    color: str
    run_id: int
    avg_eval_time: float  # Average evaluation time in milliseconds

class ScoreTableGenerator:
    """Generates HTML reports for benchmark scores and run details."""
    
    def __init__(self, session: Optional[object] = None):
        """Initialize generator with optional database session."""
        self.session = session or datastore.common.create_dev_session()
        self.template_env = Environment(loader=FileSystemLoader(constants.TEMPLATES_DIR))
       
    def _get_color(self, score: int) -> str:
        """
        Convert a score (0-100) to an RGB color value using a muted color scheme.

        Parameters:
            score (int): Score value between 0 and 100

        Returns:
            str: RGB color string (e.g., "rgb(144, 190, 144)")
        """
        if score == 100:
            return "rgb(13, 71, 161)"  # dark blue

        # Convert score to value between 0 and 1
        normalized = score / 100.0

        # Base colors for interpolation
        if (score > 70):
            low_r, low_g, low_b = 530, 400, -70  # not reached
            high_r, high_g, high_b = 30, 100, 230
        else:  # score <= 70
            low_r, low_g, low_b = 230, 140, 60  # light orange
            high_r, high_g, high_b = 230, 230, 60  # green?  not reached

        # Interpolate between the colors
        red = int(low_r + (high_r - low_r) * normalized)
        green = int(low_g + (high_g - low_g) * normalized)
        blue = int(low_b + (high_b - low_b) * normalized)

        return f"rgb({red}, {green}, {blue})"

    def _calculate_avg_eval_time(self, run_id: int) -> float:
        """
        Calculate average evaluation time for a run.
        
        Parameters:
            run_id (int): ID of the run
            
        Returns:
            float: Average evaluation time in milliseconds
        """
        run_data = datastore.benchmarks.get_run_by_run_id(run_id, self.session)
        if not run_data or not run_data['details']:
            return 0.0
            
        eval_times = [detail['eval_msec'] for detail in run_data['details'] 
                     if detail['eval_msec'] is not None]
        if not eval_times:
            return 0.0
            
        return sum(eval_times) / len(eval_times)

    def _get_dashboard_data(self) -> Dict:
        """
        Gather all data needed for the dashboard.
        
        Returns:
            dict: Dictionary containing models, benchmarks, and scores data
        """
        # Get model data sorted by size and name
        llms = datastore.common.list_all_models(self.session)
        llms.sort(key=lambda x: (x["filesize_mb"], x["displayname"]))

        # Get benchmark information
        benchmarks_list = datastore.benchmarks.list_all_benchmarks(self.session)

        # Get scores and add color and timing information
        scores = datastore.benchmarks.get_highest_benchmark_scores(self.session)
        
        # Filter out models with zero benchmark results
        models_with_results = set()
        for key in scores:
            _, model_name = key
            models_with_results.add(model_name)
            
            score_data = scores[key]
            avg_time = self._calculate_avg_eval_time(score_data["run_id"])
            scores[key] = ScoreData(
                value=score_data["score"],
                color=self._get_color(score_data["score"]),
                run_id=score_data["run_id"],
                avg_eval_time=avg_time
            ).__dict__
            
        # Filter the models list to only include those with benchmark results
        llms = [model for model in llms if model["codename"] in models_with_results]

        return {
            "llms": llms,
            "benchmarks": benchmarks_list,
            "scores": scores
        }

    def generate_dashboard(self) -> None:
        """Generate the main dashboard HTML file."""
        data = self._get_dashboard_data()
        template = self.template_env.get_template('model_scores.html')
        
        # Ensure output directory exists
        os.makedirs(constants.OUTPUT_DIR, exist_ok=True)
        
        # Render and write dashboard
        output_path = os.path.join(constants.OUTPUT_DIR, 'model_summary.html')
        with open(output_path, 'w') as f:
            f.write(template.render(data=data))

    def _write_run_detail(self, run_details: Dict) -> None:
        """
        Write run details to an HTML file.
        
        Parameters:
            run_details (dict): Dictionary containing run details
        """
        if not run_details:
            return
        
        template = self.template_env.get_template('run_details.html')
        
        # Get system prompt (context) for this benchmark
        system_prompt = self._get_context_from_benchmark(run_details['benchmark_name'])
        
        # Ensure output directories exist
        os.makedirs(os.path.join(constants.OUTPUT_DIR, "run_details"), exist_ok=True)
        
        # Write run details to file
        run_path = os.path.join(
            constants.OUTPUT_DIR, 
            "run_details", 
            f"{run_details['run_id']}.html"
        )
        with open(run_path, 'w') as f:
            f.write(template.render(run_details=run_details, system_prompt=system_prompt))

    def generate_run_detail_by_id(self, run_id: int) -> None:
        """
        Generate detailed HTML report for a specific run ID.
        
        Parameters:
            run_id (int): ID of the run to generate details for
        """
        run = self.session.query(datastore.benchmarks.Run).get(run_id)
        if not run:
            return
            
        data = datastore.benchmarks.get_run_by_run_id(run_id, self.session)
        self._write_run_detail(data)

    def generate_run_detail(self, model_name: str, benchmark_name: str) -> None:
        """
        Generate detailed HTML report for highest-scoring benchmark run.
        
        Parameters:
            model_name (str): Name of the model
            benchmark_name (str): Name of the benchmark
        """
        highest_scores = datastore.benchmarks.get_highest_benchmark_scores(self.session)
        key = (benchmark_name, model_name)
        
        if key in highest_scores:
            run_id = highest_scores[key]['run_id']
            data = datastore.benchmarks.get_run_by_run_id(run_id, self.session)
            self._write_run_detail(data)

    def _get_context_from_benchmark(self, benchmark_name: str) -> Optional[str]:
        """
        Get the system prompt (context) for a specific benchmark using the registry.
        
        Parameters:
            benchmark_name (str): Name of the benchmark
            
        Returns:
            str: System prompt text or None if not available
        """
        try:
            # Import here to avoid circular imports
            import lib.benchmarks.registry
            from lib.benchmarks.factory import get_runner

            # Create a dummy question to pass to prepare_prompt
            dummy_question = {
                "question_text": "Sample question",
                "answer_type": "free_text",
                "correct_answer": "Sample answer"
            }
            
            # Get a runner instance for this benchmark (with a dummy model name)
            runner = get_runner(benchmark_name, "dummy_model")
            if runner:
                # Call prepare_prompt to get the context
                _, _, context = runner.prepare_prompt(dummy_question)
                return context
        except Exception as e:
            logging.error(f"Error getting context for benchmark {benchmark_name}: {e}")
        
        return None

# Create default generator instance
generator = ScoreTableGenerator()

def generate_dashboard(session: Optional[object] = None) -> None:
    """Generate the main dashboard HTML file using default generator."""
    if session:
        ScoreTableGenerator(session).generate_dashboard()
    else:
        generator.generate_dashboard()

def generate_run_detail_by_id(run_id: int, session: Optional[object] = None) -> None:
    """
    Generate detailed HTML report for a specific run ID.
    
    Parameters:
        run_id (int): ID of the run to generate details for
        session (object, optional): SQLAlchemy session
    """
    if session:
        ScoreTableGenerator(session).generate_run_detail_by_id(run_id)
    else:
        generator.generate_run_detail_by_id(run_id)
