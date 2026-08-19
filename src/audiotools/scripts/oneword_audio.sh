#!/bin/bash

# Script to generate Lithuanian audio for a single word using all 3 voices
# and then sync to production server
#
# Usage: ./oneword_audio.sh <lithuanian_word>
# Example: ./oneword_audio.sh vilkas

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENAUDIO_SCRIPT="$SCRIPT_DIR/../outetts/genaudio_outetts.py"
LOCAL_CACHE_DIR="$SCRIPT_DIR/../lithuanian-audio-cache"

# Remote server configuration
REMOTE_USER="atacama"
REMOTE_HOST="137.184.45.132"
REMOTE_DIR="/home/atacama/trakaido"

# Available Lithuanian speakers
SPEAKERS=("ash" "alloy" "nova")

# Parse arguments
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <lithuanian_word>"
    echo "Example: $0 vilkas"
    echo ""
    echo "This script will:"
    echo "  1. Generate audio for the word using all 3 Lithuanian voices (ash, alloy, nova)"
    echo "  2. Store files in the lithuanian-audio-cache directory"
    echo "  3. Copy the new files to the production server"
    exit 1
fi

LITHUANIAN_WORD="$1"

# Validate that the word contains only valid Lithuanian characters
if [[ ! "$LITHUANIAN_WORD" =~ ^[a-zA-ZaąbcčdeęėfghiįyjklmnoprsštuųūvzžAĄBCČDEĘĖFGHIĮYJKLMNOPRSŠTUŲŪVZŽ\ \-_]+$ ]]; then
    echo "Error: '$LITHUANIAN_WORD' contains invalid characters for Lithuanian text"
    echo "Valid characters: Lithuanian letters (a-z, ą, č, ę, ė, į, š, ų, ū, ž), spaces, hyphens, underscores"
    exit 1
fi

# Check if required script exists
if [[ ! -f "$GENAUDIO_SCRIPT" ]]; then
    echo "Error: Audio generation script not found: $GENAUDIO_SCRIPT"
    exit 1
fi

# Check if local cache directory exists
if [[ ! -d "$LOCAL_CACHE_DIR" ]]; then
    echo "Error: Local cache directory does not exist: $LOCAL_CACHE_DIR"
    exit 1
fi

echo "Generating Lithuanian audio for word: '$LITHUANIAN_WORD'"
echo "Using speakers: ${SPEAKERS[*]}"
echo ""

# Generate audio for each speaker
SUCCESS_COUNT=0
TOTAL_COUNT=${#SPEAKERS[@]}

for speaker in "${SPEAKERS[@]}"; do
    echo "Generating audio with speaker: $speaker"
    
    # Run the audio generation script
    if PYTHONPATH="$SCRIPT_DIR/../.." python3 "$GENAUDIO_SCRIPT" --lithuanian "$LITHUANIAN_WORD" --lithuanian-speaker "$speaker" --format mp3; then
        echo "✓ Successfully generated audio with $speaker speaker"
        ((SUCCESS_COUNT++))
    else
        echo "✗ Failed to generate audio with $speaker speaker"
    fi
    echo ""
done

echo "Audio generation completed: $SUCCESS_COUNT/$TOTAL_COUNT speakers successful"

if [[ $SUCCESS_COUNT -eq 0 ]]; then
    echo "Error: No audio files were generated successfully"
    exit 1
fi

echo ""
echo "Copying audio files to production server..."

# Sanitize the word for filename (convert to lowercase, replace spaces with underscores)
SANITIZED_WORD=$(echo "$LITHUANIAN_WORD" | tr '[:upper:]' '[:lower:]' | sed 's/ /_/g')

# Create remote directories if needed
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '$REMOTE_DIR/ash' '$REMOTE_DIR/alloy' '$REMOTE_DIR/nova'" 2>/dev/null || {
    echo "Error: Cannot create remote directories"
    exit 1
}

# Copy each generated audio file
COPY_SUCCESS_COUNT=0
COPY_TOTAL_COUNT=0

for speaker in "${SPEAKERS[@]}"; do
    LOCAL_FILE="$LOCAL_CACHE_DIR/$speaker/${SANITIZED_WORD}.mp3"
    
    if [[ -f "$LOCAL_FILE" ]]; then
        ((COPY_TOTAL_COUNT++))
        echo "Copying $speaker/${SANITIZED_WORD}.mp3..."
        
        # Use scp to copy the specific file
        if scp "$LOCAL_FILE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/$speaker/"; then
            echo "✓ Successfully copied $speaker/${SANITIZED_WORD}.mp3"
            ((COPY_SUCCESS_COUNT++))
        else
            echo "✗ Failed to copy $speaker/${SANITIZED_WORD}.mp3"
        fi
    else
        echo "⚠ Audio file not found: $LOCAL_FILE"
    fi
done

if [[ $COPY_SUCCESS_COUNT -eq 0 ]]; then
    echo "Error: No audio files were copied successfully"
    exit 1
fi

echo "File copy completed: $COPY_SUCCESS_COUNT/$COPY_TOTAL_COUNT files copied successfully"

echo ""
echo "Process completed successfully!"
echo "Generated audio for '$LITHUANIAN_WORD' with $SUCCESS_COUNT/$TOTAL_COUNT speakers and synced to production."