import os

# Get the src directory
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the project root (top-level directory)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Define common paths relative to project root
BENCHMARK_DATA = os.path.join(SRC_DIR, "benchmarks")  # TODO: split/move?
SCHEMA_DIR = os.path.join(SRC_DIR, "schema")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
