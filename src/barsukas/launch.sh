#!/bin/bash

# Launch script for Barsukas web interface
# Sets up Python path to allow imports from wordfreq module

# Default storage format
STORAGE_FORMAT="sqlite"
# Default to all interfaces
HOST_ARGS="--host 0.0.0.0"
# Optional database path
DB_PATH=""

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
        --db-path)
            DB_PATH="$2"
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
    echo "Usage: $0 [-f|--format jsonl|sqlite] [-a|--all-interfaces] [--db-path PATH]"
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
elif [[ "$STORAGE_FORMAT" == "sqlite" && -n "$DB_PATH" ]]; then
    # Make path absolute if it's relative
    if [[ "$DB_PATH" = /* ]]; then
        export BARSUKAS_DB_PATH="$DB_PATH"
    else
        export BARSUKAS_DB_PATH="$REPO_ROOT/$DB_PATH"
    fi
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
elif [[ "$STORAGE_FORMAT" == "sqlite" && -n "$BARSUKAS_DB_PATH" ]]; then
    echo "SQLite database: $BARSUKAS_DB_PATH"
fi
echo ""

# Start/stop task worker helpers
WORKER_PID=""

start_worker() {
    echo "Starting Barsukas task worker"
    python -m barsukas.workers.task_worker &
    WORKER_PID=$!
}

stop_worker() {
    local timeout_seconds=${1:-15}
    if [[ -n "$WORKER_PID" ]] && kill -0 "$WORKER_PID" 2>/dev/null; then
        echo "Stopping Barsukas task worker (pid $WORKER_PID)"
        kill -TERM "$WORKER_PID"
        local deadline=$((SECONDS + timeout_seconds))
        while (( SECONDS < deadline )); do
            if ! kill -0 "$WORKER_PID" 2>/dev/null; then
                WORKER_PID=""
                return
            fi
            sleep 0.5
        done
        echo "Worker did not stop quickly; forcing shutdown"
        kill -KILL "$WORKER_PID" 2>/dev/null
        wait "$WORKER_PID" 2>/dev/null
    fi
    WORKER_PID=""
}

cleanup() {
    stop_worker 15
}

trap cleanup EXIT INT TERM

# Run the Flask app with remaining arguments in a loop for auto-restart
# Exit code 0 = normal shutdown, don't restart
# Exit code 42 = restart requested, restart immediately
RESTART_WORKER=0
while true; do
    python app.py $HOST_ARGS "$@" &
    SERVER_PID=$!
    if [[ $RESTART_WORKER -eq 1 ]]; then
        stop_worker 60
        start_worker
        RESTART_WORKER=0
    elif [[ -z "$WORKER_PID" ]]; then
        start_worker
    fi
    wait "$SERVER_PID"
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 42 ]; then
        echo ""
        echo "=========================================="
        echo "Restarting Barsukas (exit code 42)..."
        echo "=========================================="
        echo ""
        RESTART_WORKER=1
        sleep 0.5  # Brief pause to ensure port is released
    else
        echo ""
        echo "Barsukas exited with code $EXIT_CODE"
        stop_worker 15
        exit $EXIT_CODE
    fi
done
