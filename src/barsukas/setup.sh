#!/bin/bash

# Setup script for Barsukas web interface
# Creates a Python venv and installs all required dependencies

set -e

# Default venv location
VENV_PATH=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --venv PATH"
            echo ""
            echo "Creates a Python virtual environment and installs dependencies for Barsukas."
            echo ""
            echo "Options:"
            echo "  --venv PATH    Path where the venv should be created (required)"
            echo "  -h, --help     Show this help message"
            exit 0
            ;;
        *)
            echo "Error: Unknown option '$1'"
            echo "Usage: $0 --venv PATH"
            exit 1
            ;;
    esac
done

if [[ -z "$VENV_PATH" ]]; then
    echo "Error: --venv PATH is required"
    echo "Usage: $0 --venv PATH"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get the repo root (2 levels up from barsukas)
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

echo "=========================================="
echo "Setting up Barsukas environment"
echo "=========================================="
echo "Venv path: $VENV_PATH"
echo "Repo root: $REPO_ROOT"
echo ""

# Create venv if it doesn't exist
if [[ ! -d "$VENV_PATH" ]]; then
    echo "Creating virtual environment at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
else
    echo "Virtual environment already exists at $VENV_PATH"
fi

# Activate venv
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo ""
echo "Installing dependencies from requirements.txt files..."
pip install -r "$REPO_ROOT/requirements.txt" -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "To run Barsukas:"
echo "  $SCRIPT_DIR/launch.sh --venv $VENV_PATH"
