#!/bin/bash

# Launch script for Barsukas web interface
# Sets up Python path to allow imports from wordfreq module

# Default storage format
STORAGE_FORMAT="sqlite"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--format)
            STORAGE_FORMAT="$2"
            shift 2
            ;;
        *)
            # Pass through any other arguments to the Flask app
            break
            ;;
    esac
done

# Validate storage format
if [[ "$STORAGE_FORMAT" != "jsonl" && "$STORAGE_FORMAT" != "sqlite" ]]; then
    echo "Error: Invalid storage format '$STORAGE_FORMAT'"
    echo "Usage: $0 [-f|--format jsonl|sqlite]"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get the repo root (2 levels up from barsukas)
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Set PYTHONPATH to include src/ directory
export PYTHONPATH="$REPO_ROOT/src:$PYTHONPATH"

# Configure storage backend based on format
export STORAGE_BACKEND="$STORAGE_FORMAT"
if [[ "$STORAGE_FORMAT" == "jsonl" ]]; then
    export JSONL_DATA_DIR="$REPO_ROOT/data/release"
fi

# Change to barsukas directory
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Barsukas Web Interface"
echo "=========================================="
echo "Storage backend: $STORAGE_BACKEND"
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"
if [[ "$STORAGE_FORMAT" == "jsonl" ]]; then
    echo "JSONL data directory: $JSONL_DATA_DIR"
fi
echo ""

# Run the Flask app with remaining arguments
python app.py "$@"
