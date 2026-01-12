#!/bin/bash

# Startup script for Benchmark Server

# Change to project root
cd "$(dirname "$0")"

# Set PYTHONPATH
export PYTHONPATH=src

# Run the benchmark server
python src/bench_server/app.py "$@"
