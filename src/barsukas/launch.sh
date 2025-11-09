#!/bin/bash

# Launch script for Barsukas web interface
# Sets up Python path to allow imports from wordfreq module

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get the repo root (2 levels up from barsukas)
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Set PYTHONPATH to include src/ directory
export PYTHONPATH="$REPO_ROOT/src:$PYTHONPATH"

# Change to barsukas directory
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Barsukas Web Interface"
echo "=========================================="
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"
echo ""

# Run the Flask app with any provided arguments
python app.py "$@"
