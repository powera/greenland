#!/bin/bash

# Simple script to sync Lithuanian audio cache files to remote server
# Only copies files that are different (based on size and timestamp)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$SCRIPT_DIR/lithuanian-audio-cache"
REMOTE_USER="atacama"
REMOTE_HOST="137.184.45.132"
REMOTE_DIR="/home/atacama/trakaido"

# Parse arguments
DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--verbose]"
            echo "  --dry-run    Show what would be copied without doing it"
            echo "  --verbose    Show detailed output"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if local directory exists
if [[ ! -d "$LOCAL_DIR" ]]; then
    echo "Error: Local directory does not exist: $LOCAL_DIR"
    exit 1
fi

# Build rsync options for efficient sync
RSYNC_OPTS="-az"  # archive mode + compression
RSYNC_OPTS="$RSYNC_OPTS --update"  # skip files that are newer on receiver
RSYNC_OPTS="$RSYNC_OPTS --progress"  # show progress

if [[ $DRY_RUN == true ]]; then
    RSYNC_OPTS="$RSYNC_OPTS --dry-run"
    echo "DRY RUN - showing what would be copied:"
fi

if [[ $VERBOSE == true ]]; then
    RSYNC_OPTS="$RSYNC_OPTS -v"
fi

# Create remote directory if needed and sync
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '$REMOTE_DIR'" 2>/dev/null || {
    echo "Error: Cannot create remote directory"
    exit 1
}

echo "Syncing audio files..."
rsync $RSYNC_OPTS "$LOCAL_DIR/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

if [[ $DRY_RUN == false ]]; then
    echo "Sync completed successfully"
else
    echo "Dry run completed"
fi
