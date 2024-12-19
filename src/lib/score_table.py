#!/usr/bin/python3
"""Generates HTML score tables and detailed reports for benchmark results."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader

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
            return "rgb(144, 190, 144)"  # Muted green

        # Convert score to value between 0 and 1
        normalized = score / 100.0

        # Base colors for interpolation
        low_r, low_g, low_b = 190, 144, 144  # Muted red
        high_r, high_g, high_b = 144, 190, 144  # Muted green

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
        for key in scores:
            score_data = scores[key]
            avg_time = self._calculate_avg_eval_time(score_data["run_id"])
            scores[key] = ScoreData(
                value=score_data["score"],
                color=self._get_color(score_data["score"]),
                run_id=score_data["run_id"],
                avg_eval_time=avg_time
            ).__dict__

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
        
        # Ensure output directories exist
        os.makedirs(os.path.join(constants.OUTPUT_DIR, "run_details"), exist_ok=True)
        
        # Write run details to file
        run_path = os.path.join(
            constants.OUTPUT_DIR, 
            "run_details", 
            f"{run_details['run_id']}.html"
        )
        with open(run_path, 'w') as f:
            f.write(template.render(run_details=run_details))

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
