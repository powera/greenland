#!/bin/bash

# Launch script for the Barsukas web interface.
#
# This script deliberately makes no configuration decisions: it activates a venv,
# sets PYTHONPATH, and runs unified_app.py with an auto-restart loop. Which
# databases to use is decided entirely by the persona (see src/barsukas/personas.py).
#
# For a custom database, run unified_app.py directly:
#   PYTHONPATH=src python src/barsukas/unified_app.py --db-url postgresql://...

# Default to all interfaces
HOST_ARGS="--host 0.0.0.0"
# Default port
PORT="5555"
# Python venv path (optional)
VENV_PATH=""
# Persona (optional; Python defaults to 'local')
PERSONA=""

usage() {
    cat <<'EOF'
Usage: launch.sh [--persona NAME] [-p|--port PORT] [-a|--all-interfaces] [--venv PATH]

  --persona NAME   Launch persona (default: local). --list-personas to see them.
  -p, --port       Port to listen on (default: 5555)
  -a               Bind all interfaces (default)
  --venv PATH      Activate this virtualenv first
  --list-personas  List available personas and exit

Any other arguments are passed through to unified_app.py.
EOF
}

# Tell the developer where a removed flag went, rather than silently ignoring it.
removed_flag() {
    echo "Error: $1 was removed from launch.sh."
    echo "       $2"
    exit 1
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--all-interfaces)
            HOST_ARGS="--host 0.0.0.0"
            shift
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#*=}"
            shift
            ;;
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        --venv=*)
            VENV_PATH="${1#*=}"
            shift
            ;;
        --persona)
            PERSONA="$2"
            shift 2
            ;;
        --persona=*)
            PERSONA="${1#*=}"
            shift
            ;;
        -f|--format|--format=*)
            removed_flag "--format" "The persona picks the storage backend: --persona local|local-sqlite|golden|scholar|prod"
            ;;
        --postgres)
            removed_flag "--postgres" "Use --persona prod, or run unified_app.py directly with --db-url postgresql://..."
            ;;
        --db-path|--db-path=*)
            removed_flag "--db-path" "Set BARSUKAS_DB_PATH, or run unified_app.py directly with --db-url"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            # Pass through any other arguments to the Flask app
            break
            ;;
    esac
done

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

PERSONA_ARGS=""
if [[ -n "$PERSONA" ]]; then
    PERSONA_ARGS="--persona $PERSONA"
fi

# Change to barsukas directory
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Barsukas Web Interface (Unified Mode)"
echo "=========================================="
if [[ -n "$VENV_PATH" ]]; then
    echo "Python venv: $VENV_PATH"
fi
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"
echo ""
echo "NOTE: Using unified launcher (Flask + Worker in same process)"
echo "      Persona and database selection are reported below by the app."
echo ""

cleanup() {
    # Prevent re-entrant cleanup (EXIT trap can run after INT/TERM trap)
    if [[ "${SHUTDOWN_IN_PROGRESS:-0}" -eq 1 ]]; then
        return
    fi
    SHUTDOWN_IN_PROGRESS=1

    echo ""
    echo "Shutting down Barsukas..."

    # Stop the unified server process group if it's running.
    # Using a process group ensures child processes are terminated too.
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        local server_pgid="${SERVER_PGID:-$SERVER_PID}"
        echo "Stopping Barsukas server process group (pgid $server_pgid)"

        # Ask for graceful shutdown first
        kill -TERM "-$server_pgid" 2>/dev/null || true

        # Give the process group a moment to shut down cleanly
        for _ in {1..20}; do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done

        # Escalate if still alive
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "Server still running; force-killing process group (pgid $server_pgid)"
            kill -KILL "-$server_pgid" 2>/dev/null || true
        fi

        wait "$SERVER_PID" 2>/dev/null || true
    fi
}

handle_signal() {
    cleanup
    exit 130
}

trap handle_signal INT TERM
trap cleanup EXIT

# Run the unified app (Flask + Worker in same process) in a loop for auto-restart
# Exit code 0 = normal shutdown, don't restart
# Exit code 42 = restart requested, restart immediately
while true; do
    # Start in a dedicated process group so Ctrl+C cleanup can stop all children.
    # setsid is Linux-only; on macOS, use perl to call POSIX::setsid().
    if command -v setsid >/dev/null 2>&1; then
        setsid python unified_app.py $HOST_ARGS --port "$PORT" $PERSONA_ARGS "$@" &
    else
        perl -e 'use POSIX qw(setsid); setsid(); exec @ARGV' \
            python unified_app.py $HOST_ARGS --port "$PORT" $PERSONA_ARGS "$@" &
    fi
    SERVER_PID=$!
    SERVER_PGID=$SERVER_PID
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
