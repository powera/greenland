#!/usr/bin/python3

"""Script runner with logging setup."""

import os
import sys
import logging
import argparse
import traceback

def run_script(script_path: str, args: list) -> None:
    """
    Run a Python script from the scripts directory.
    
    Args:
        script_path: Path to script relative to scripts directory
        args: Additional command line arguments to pass to script
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Modify sys.argv to pass remaining args to script
    sys.argv = [script_path] + args
    
    # Add scripts prefix if not present
    if not script_path.startswith("scripts."):
        script_path = f"scripts.{script_path}"
    
    # Import and run the script
    try:
        __import__(script_path).main()
    except Exception:
        logging.error("Error running script:\n%s", traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a script with additional arguments")
    parser.add_argument("script", help="Script name to run (e.g. run_all_quals or scripts.run_all_quals)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to script")
    args = parser.parse_args()
        
    run_script(args.script, args.args)
