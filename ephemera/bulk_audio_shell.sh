#!/bin/bash
# Generate audio for trakaido levels 1-10 across de/it/nl/pt/sv.
# Uploads to S3 staging as pending_review; ungurys exports unreviewed audio for now.
set -euo pipefail

for lang in lt es fr zh; do
  echo "=== Generating audio for $lang ==="
  PYTHONPATH=src python src/agents/vieversys.py \
    --mode populate-only \
    --language "$lang" \
    --level 1-20 \
    --upload-s3 \
    --yes
done

for lang in de it nl pt sv; do
  echo "=== Generating audio for $lang ==="
  PYTHONPATH=src python src/agents/vieversys.py \
    --mode populate-only \
    --language "$lang" \
    --level 1-10 \
    --upload-s3 \
    --yes
done
