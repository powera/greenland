#!/bin/bash

# Batch wordlists live in the audio/ submodule (github.com/powera/audiotools),
# which is not part of this tree. Point BATCHES_DIR at that checkout, e.g.
#   BATCHES_DIR=../../../audio/batches ./runall.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BATCHES_DIR="${BATCHES_DIR:-$REPO_ROOT/audio/batches}"

if [[ ! -d "$BATCHES_DIR" ]]; then
    echo "Batches directory not found: $BATCHES_DIR" >&2
    echo "Set BATCHES_DIR to your audio/ submodule's batches directory." >&2
    exit 1
fi

# List of wordlist files
wordlists=("words10.txt")

# List of speakers
speakers=("ash" "alloy" "nova")

# Loop over each wordlist and speaker
for wordlist in "${wordlists[@]}"; do
    for speaker in "${speakers[@]}"; do
        echo "Generating audio for $wordlist with speaker $speaker"
        PYTHONPATH="$REPO_ROOT/src" python3 "$SCRIPT_DIR/../outetts/genaudio_outetts.py" \
            --lithuanian-speaker="$speaker" \
            --format=mp3 \
            --lithuanian-batch="$BATCHES_DIR/$wordlist"
    done
done

"$SCRIPT_DIR/copy_audio_cache.sh"
