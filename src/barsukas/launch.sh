#!/bin/bash

# Launch script for Barsukas web interface
# Sets up Python path to allow imports from wordfreq module

# Default storage format
STORAGE_FORMAT="sqlite"
# Default to all interfaces
HOST_ARGS="--host 0.0.0.0"
# Default port
PORT="5555"
# Optional database path
DB_PATH=""
# PostgreSQL mode
USE_POSTGRES=""
# Python venv path (optional)
VENV_PATH=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--format)
            STORAGE_FORMAT="$2"
            shift 2
            ;;
        -a|--all-interfaces)
            HOST_ARGS="--host 0.0.0.0"
            shift
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        --db-path)
            DB_PATH="$2"
            shift 2
            ;;
        --postgres)
            USE_POSTGRES="true"
            shift
            ;;
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        *)
            # Pass through any other arguments to the Flask app
            break
            ;;
    esac
done

# Validate storage format (only if not using postgres)
if [[ -z "$USE_POSTGRES" && "$STORAGE_FORMAT" != "jsonl" && "$STORAGE_FORMAT" != "sqlite" ]]; then
    echo "Error: Invalid storage format '$STORAGE_FORMAT'"
    echo "Usage: $0 [-f|--format jsonl|sqlite] [--postgres] [-a|--all-interfaces] [-p|--port PORT] [--db-path PATH] [--venv PATH]"
    exit 1
fi

# Activate venv if specified
if [[ -n "$VENV_PATH" ]]; then
    if [[ -f "$VENV_PATH/bin/activate" ]]; then
        source "$VENV_PATH/bin/activate"
    else
        echo "Error: Cannot find venv at '$VENV_PATH' (no bin/activate found)"
        exit 1
    fi
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get the repo root (2 levels up from barsukas)
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Set PYTHONPATH to include src/ directory
export PYTHONPATH="$REPO_ROOT/src:$PYTHONPATH"

# Configure storage backend based on format
if [[ -n "$USE_POSTGRES" ]]; then
    export STORAGE_BACKEND="postgres"
    export USE_POSTGRES_BACKEND="true"
else
    export STORAGE_BACKEND="$STORAGE_FORMAT"
    if [[ "$STORAGE_FORMAT" == "jsonl" ]]; then
        export JSONL_DATA_DIR="$REPO_ROOT/data/release"
    elif [[ "$STORAGE_FORMAT" == "sqlite" && -n "$DB_PATH" ]]; then
        # Make path absolute if it's relative
        if [[ "$DB_PATH" = /* ]]; then
            export BARSUKAS_DB_PATH="$DB_PATH"
        else
            export BARSUKAS_DB_PATH="$REPO_ROOT/$DB_PATH"
        fi
    fi
fi

# Change to barsukas directory
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Barsukas Web Interface (Unified Mode)"
echo "=========================================="
if [[ -n "$VENV_PATH" ]]; then
    echo "Python venv: $VENV_PATH"
fi
echo "Storage backend: $STORAGE_BACKEND"
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"
if [[ -n "$USE_POSTGRES" ]]; then
    echo "PostgreSQL mode: enabled (using postgres_ul + keys/postgres.key)"
elif [[ "$STORAGE_FORMAT" == "jsonl" ]]; then
    echo "JSONL data directory: $JSONL_DATA_DIR"
elif [[ "$STORAGE_FORMAT" == "sqlite" && -n "$BARSUKAS_DB_PATH" ]]; then
    echo "SQLite database: $BARSUKAS_DB_PATH"
fi
echo ""
echo "NOTE: Using unified launcher (Flask + Worker in same process)"
if [[ -z "$USE_POSTGRES" ]]; then
    echo "      This avoids SQLite concurrency issues."
fi
echo ""

cleanup() {
    echo ""
    echo "Shutting down Barsukas..."

    # Stop the unified server if it's running
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Stopping Barsukas server (pid $SERVER_PID)"
        kill -TERM "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
}

trap cleanup EXIT INT TERM

# Run the unified app (Flask + Worker in same process) in a loop for auto-restart
# Exit code 0 = normal shutdown, don't restart
# Exit code 42 = restart requested, restart immediately
while true; do
    python unified_app.py $HOST_ARGS --port "$PORT" "$@" &
    SERVER_PID=$!
    wait "$SERVER_PID"
    EXIT_CODE=$?

    # If wait was interrupted by signal (exit code > 128), cleanup will handle it
    if [ $EXIT_CODE -gt 128 ]; then
        exit $EXIT_CODE
    elif [ $EXIT_CODE -eq 42 ]; then
        echo ""
        echo "=========================================="
        echo "Restarting Barsukas (exit code 42)..."
        echo "=========================================="
        echo ""
        sleep 0.5  # Brief pause to ensure port is released
    else
        echo ""
        echo "Barsukas exited with code $EXIT_CODE"
        exit $EXIT_CODE
    fi
done
