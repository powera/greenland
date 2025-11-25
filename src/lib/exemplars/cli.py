#!/usr/bin/python3

"""
Command-line tool for running exemplars and generating reports.
"""

import argparse
import importlib
import os
import sys
from typing import List, Optional

from lib.exemplars.base import (
    registry, runner, storage, report_generator,
    run_exemplar, compare_models, generate_report, generate_all_reports
)
import benchmarks.datastore.common

def load_exemplar_modules():
    """Dynamically load all exemplar modules to register them."""
    exemplars_dir = os.path.join(os.path.dirname(__file__), "lib", "exemplars", "tasks")
    
    if not os.path.exists(exemplars_dir):
        print(f"Warning: Exemplars directory not found: {exemplars_dir}")
        return
        
    for filename in os.listdir(exemplars_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]  # Remove .py extension
            import_path = f"lib.exemplars.tasks.{module_name}"
            
            try:
                importlib.import_module(import_path)
                print(f"Loaded exemplar module: {import_path}")
            except ImportError as e:
                print(f"Error loading exemplar module {import_path}: {e}")

def list_exemplars():
    """List all registered exemplars."""
    exemplars = registry.list_exemplars()
    
    if not exemplars:
        print("No exemplars registered.")
        return
        
    print(f"\n{'=' * 80}")
    print(f"{'ID':<30} {'Name':<30} {'Type':<20}")
    print(f"{'-' * 30} {'-' * 30} {'-' * 20}")
    
    for exemplar in exemplars:
        type_str = exemplar.type.value if hasattr(exemplar.type, "value") else exemplar.type
        print(f"{exemplar.id:<30} {exemplar.name:<30} {type_str:<20}")
        
    print(f"{'=' * 80}\n")

def list_models():
    """List all available models from the database."""
    # Use the runner's method to get models
    models = runner.get_available_models()
    
    if not models:
        print("No models registered in the database.")
        return
        
    print(f"\n{'=' * 80}")
    print(f"{'Codename':<40} {'Display Name':<40}")
    print(f"{'-' * 40} {'-' * 40}")
    
    for model in models:
        print(f"{model['codename']:<40} {model['displayname']:<40}")
        
    print(f"{'=' * 80}\n")

def run_single_exemplar(exemplar_id: str, model_names: List[str] = None, generate_html: bool = True):
    """
    Run a single exemplar with specified models.
    
    Args:
        exemplar_id: ID of the exemplar to run
        model_names: List of model names to use (if None, uses models from database)
        generate_html: Whether to generate an HTML report
    """
    # Get models from database if not specified
    if model_names is None:
        model_names = runner.get_model_names()[:3]  # Use top 3 models by default
        if not model_names:
            print("No models found in database. Using default model.")
            model_names = ["gpt-4o-mini-2024-07-18"]
    
    print(f"Running exemplar '{exemplar_id}' with models: {', '.join(model_names)}")
    
    # Validate exemplar exists
    if not registry.get_exemplar(exemplar_id):
        print(f"Error: Exemplar '{exemplar_id}' not found.")
        return
        
    # Run the exemplar with each model
    results = compare_models(exemplar_id, model_names)
    
    # Print brief results
    for result in results:
        print(f"\nModel: {result.model_name}")
        print(f"Response length: {len(result.response_text)} chars")
        print(f"Tokens: {result.metadata.get('tokens', 'N/A')}")
        print(f"Time: {result.metadata.get('timing_ms', 'N/A')}ms")
        
    # Generate HTML report if requested
    if generate_html:
        report_path = generate_report(exemplar_id)
        print(f"\nReport generated: {report_path}")

def run_all_exemplars(model_name: str = None, generate_html: bool = True):
    """
    Run all exemplars with a specific model.
    
    Args:
        model_name: Name of the model to use (if None, uses first model from database)
        generate_html: Whether to generate HTML reports
    """
    # Get model from database if not specified
    if model_name is None:
        model_names = runner.get_model_names()
        if model_names:
            model_name = model_names[0]
        else:
            print("No models found in database. Using default model.")
            model_name = "gpt-4o-mini-2024-07-18"
    
    exemplars = registry.list_exemplars()
    
    if not exemplars:
        print("No exemplars registered.")
        return
        
    print(f"Running all exemplars with model: {model_name}")
    
    for exemplar in exemplars:
        print(f"\nRunning exemplar: {exemplar.id}")
        run_exemplar(exemplar.id, model_name)
        
    # Generate HTML reports if requested
    if generate_html:
        report_generator.generate_all_reports()
        index_path = report_generator.generate_index_report()
        print(f"\nIndex report generated: {index_path}")

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Run and manage exemplars")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List exemplars or models")
    list_parser.add_argument("--models", action="store_true", help="List available models")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run exemplars")
    run_parser.add_argument("exemplar_id", nargs="?", help="ID of the exemplar to run (omit for all)")
    run_parser.add_argument("--models", nargs="+", help="Model(s) to run the exemplar with")
    run_parser.add_argument("--no-html", action="store_true", help="Skip HTML report generation")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate reports")
    report_parser.add_argument("exemplar_id", nargs="?", help="ID of the exemplar to generate a report for (omit for all)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Load all exemplar modules
    load_exemplar_modules()
    
    # Handle commands
    if args.command == "list":
        if args.models:
            list_models()
        else:
            list_exemplars()
            
    elif args.command == "run":
        if args.exemplar_id:
            # Run a specific exemplar with specified models
            models = args.models if args.models else None  # Will use database models by default
            run_single_exemplar(args.exemplar_id, models, not args.no_html)
        else:
            # Run all exemplars with a specific model
            model = args.models[0] if args.models else None  # Will use first database model by default
            run_all_exemplars(model, not args.no_html)
            
    elif args.command == "report":
        if args.exemplar_id:
            # Generate report for a specific exemplar
            report_path = generate_report(args.exemplar_id)
            print(f"Report generated: {report_path}")
        else:
            # Generate reports for all exemplars
            generate_all_reports()
            print("All reports generated.")
            
    else:
        # No command specified, show help
        parser.print_help()

if __name__ == "__main__":
    main()