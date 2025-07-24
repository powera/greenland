# Greenland Project Information

## Summary
Greenland is a benchmark suite for language models with a simple HTML server for running various NLP tasks. It provides a framework for evaluating LLM performance on linguistic tasks, creating what the project describes as "functions for words" - essentially a calculator that operates on paragraphs of text.

## Structure
- **src/**: Core Python code including clients, benchmarks, and utilities
  - **clients/**: Implementations for various LLM providers (OpenAI, Anthropic, Ollama, etc.)
  - **benchmarks/**: Test suites for evaluating LLM capabilities
  - **lib/**: Core libraries for running benchmarks and evaluations
  - **wordfreq/**: Word frequency analysis and linguistic processing
  - **verbalator/**: HTTP server for handling LLM generation requests
  - **util/**: Utility functions for text processing
- **public_html/**: Web interface files (CSS, JS, images)
- **templates/**: HTML templates for displaying results
- **data/**: Word frequency data and wordlists

## Language & Runtime
**Language**: Python
**Version**: Python 3.9+
**Build System**: setuptools
**Package Manager**: pip

## Dependencies
**Main Dependencies**:
- sqlalchemy (≥2.0.0): SQL database ORM
- jinja2 (≥3.1.0): HTML templating
- requests (≥2.31.0): HTTP client
- tiktoken (≥0.5.0): Token counting for LLMs
- pypinyin (≥0.53.0): Chinese pinyin conversion
- jieba (≥0.42.1): Chinese text segmentation

**Development Dependencies**:
- pytest (≥7.0.0): Testing framework
- black (≥23.0.0): Code formatter
- mypy (≥1.0.0): Type checking

**Optional ML Dependencies**:
- torch (≥2.0.0): Machine learning framework
- transformers (≥4.35.0): Hugging Face transformers
- whisper (≥1.0): Speech recognition
- accelerate (≥0.25.0): Distributed training
- datasets (≥2.14.0): Dataset handling

## Build & Installation
```bash
# Install basic dependencies
pip install -r requirements.txt

# Install with development dependencies
pip install -e ".[dev]"

# Install with machine learning dependencies
pip install -e ".[ml]"
```

## Main Components

### Benchmark System
The core benchmark system evaluates LLM performance on various linguistic tasks. Benchmarks are organized in the `src/benchmarks/` directory with categories like spell checking, translation, and knowledge testing.

**Run Command**:
```bash
python -m src.run_script lib.run_benchmark --benchmark [benchmark_code]
```

### Verbalator Server
A HTTP server that handles LLM generation requests, providing a web interface for running linguistic tasks.

**Run Command**:
```bash
python -m src.verbalator.server
```

### Unified LLM Client
A client system that routes requests to appropriate LLM backends (OpenAI, Anthropic, Ollama, etc.) based on model name.

### Word Frequency Analysis
Tools for linguistic analysis including word frequency processing, POS tagging, and text evaluation.

## Testing
**Framework**: pytest
**Test Location**: `src/tests/`
**Naming Convention**: Files prefixed with `test_`
**Run Command**:
```bash
python run_tests.py
```