#!/usr/bin/python3
"""Generates HTML score tables and detailed reports for benchmark results."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader

import benchmarks.datastore
import constants

@dataclass
class ScoreData:
    """Represents score data for a benchmark run."""
    value: int
    color: str
    run_id: int

class ScoreTableGenerator:
    """Generates HTML reports for benchmark scores and run details."""
    
    def __init__(self, session: Optional[object] = None):
        """Initialize generator with optional database session."""
        self.session = session or benchmarks.datastore.create_dev_session()
        self.template_env = Environment(loader=FileSystemLoader(constants.TEMPLATES_DIR))
        
    def _get_color(self, score: int) -> str:
        """
        Convert a score (0-100) to an RGB color value.
        
        Parameters:
            score (int): Score value between 0 and 100
            
        Returns:
            str: RGB color string (e.g., "rgb(0, 255, 0)")
        """
        if score == 100:
            return "rgb(0, 255, 0)"
        
        # Convert score to value between 0 and 1
        normalized = score / 100.0
        
        # Calculate red and green components
        red = int(40 + 215 * (1 - normalized))
        green = int(215 * normalized)
        
        return f"rgb({red}, {green}, 0)"

    def _get_dashboard_data(self) -> Dict:
        """
        Gather all data needed for the dashboard.
        
        Returns:
            dict: Dictionary containing models, benchmarks, and scores data
        """
        # Get model data sorted by size and name
        llms = benchmarks.datastore.list_all_models(self.session)
        llms.sort(key=lambda x: (x["filesize_mb"], x["displayname"]))

        # Get benchmark information
        benchmark_info = benchmarks.datastore.list_all_benchmarks(self.session)
        for benchmark in benchmark_info:
            benchmark["longname"] = f'{benchmark["codename"]}:{benchmark["metric"]}'

        # Get scores and add color information
        scores = benchmarks.datastore.get_highest_benchmark_scores(self.session)
        for key in scores:
            score_data = scores[key]
            scores[key] = ScoreData(
                value=score_data["score"],
                color=self._get_color(score_data["score"]),
                run_id=score_data["run_id"]
            ).__dict__

        return {
            "llms": llms,
            "benchmarks": benchmark_info,
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
        run = self.session.query(benchmarks.datastore.Run).get(run_id)
        if not run:
            return
            
        data = benchmarks.datastore.get_run_by_run_id(run_id, self.session)
        self._write_run_detail(data)

    def generate_run_detail(self, model_name: str, benchmark_name: str, 
                          benchmark_metric: str) -> None:
        """
        Generate detailed HTML report for a specific benchmark run.

        Largely obsolete; but still possibly used for a "Hall of Fame".
        
        Parameters:
            model_name (str): Name of the model
            benchmark_name (str): Name of the benchmark
            benchmark_metric (str): Metric used for the benchmark
        """
        data = benchmarks.datastore.get_highest_scoring_run_details(
            self.session,
            model_name,
            benchmark_name,
            benchmark_metric
        )
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
