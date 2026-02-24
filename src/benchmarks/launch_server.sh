#!/bin/bash

# Startup script for Benchmark Server

# Get the script's directory and go to project root
cd "$(dirname "$0")/../.."

# Set PYTHONPATH
export PYTHONPATH=src

# Run the benchmark server
python src/benchmarks/server/app.py "$@" --host=0.0.0.0
