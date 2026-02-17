#!/usr/bin/python3

"""Compatibility CLI entrypoint for benchmark commands."""

import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent

    # Ensure the package import resolves to src/benchmarks package, not this file.
    sys.path = [p for p in sys.path if Path(p).resolve() != script_dir]
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    runpy.run_module("benchmarks.run_benchmark", run_name="__main__")
