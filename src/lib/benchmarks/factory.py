#!/usr/bin/python3

"""Factory for creating benchmark generators and runners."""

import logging
from typing import Dict, Optional, Type, Any

from lib.benchmarks.base import BenchmarkGenerator, BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Registry dictionaries to store generator and runner classes
_generator_registry: Dict[str, Type[BenchmarkGenerator]] = {}
_runner_registry: Dict[str, Type[BenchmarkRunner]] = {}

# Registry for benchmark metadata
_benchmark_metadata: Dict[str, BenchmarkMetadata] = {}


def register_generator(benchmark_code: str, generator_class: Type[BenchmarkGenerator]) -> None:
    """
    Register a generator class for a benchmark code.
    
    Args:
        benchmark_code: Unique benchmark identifier
        generator_class: Generator class to register
    """
    _generator_registry[benchmark_code] = generator_class
    logger.debug("Registered generator %s for benchmark %s", 
                generator_class.__name__, benchmark_code)


def register_runner(benchmark_code: str, runner_class: Type[BenchmarkRunner]) -> None:
    """
    Register a runner class for a benchmark code.
    
    Args:
        benchmark_code: Unique benchmark identifier
        runner_class: Runner class to register
    """
    _runner_registry[benchmark_code] = runner_class
    logger.debug("Registered runner %s for benchmark %s", 
                runner_class.__name__, benchmark_code)


def register_benchmark_metadata(metadata: BenchmarkMetadata) -> None:
    """
    Register metadata for a benchmark.
    
    Args:
        metadata: Benchmark metadata object
    """
    _benchmark_metadata[metadata.code] = metadata
    logger.debug("Registered metadata for benchmark %s", metadata.code)


def get_generator(benchmark_code: str, session=None) -> Optional[BenchmarkGenerator]:
    """
    Get generator instance for a benchmark code.
    
    Args:
        benchmark_code: Unique benchmark identifier
        session: Optional database session
        
    Returns:
        Instance of the registered generator class or None if not found
    """
    if benchmark_code not in _generator_registry:
        logger.error("No generator registered for benchmark %s", benchmark_code)
        return None
        
    if benchmark_code not in _benchmark_metadata:
        logger.error("No metadata registered for benchmark %s", benchmark_code)
        return None
    
    generator_class = _generator_registry[benchmark_code]
    metadata = _benchmark_metadata[benchmark_code]
    
    return generator_class(metadata, session)


def get_runner(benchmark_code: str, model: str) -> Optional[BenchmarkRunner]:
    """
    Get runner instance for a benchmark code and model.
    
    Args:
        benchmark_code: Unique benchmark identifier
        model: Model name to benchmark
        
    Returns:
        Instance of the registered runner class or None if not found
    """
    if benchmark_code not in _runner_registry:
        logger.error("No runner registered for benchmark %s", benchmark_code)
        return None
        
    if benchmark_code not in _benchmark_metadata:
        logger.error("No metadata registered for benchmark %s", benchmark_code)
        return None
    
    runner_class = _runner_registry[benchmark_code]
    metadata = _benchmark_metadata[benchmark_code]
    
    return runner_class(model, metadata)


def get_all_benchmark_codes() -> list[str]:
    """
    Get a list of all registered benchmark codes.
    
    Returns:
        List of benchmark codes
    """
    return list(_benchmark_metadata.keys())


def get_benchmark_metadata(benchmark_code: str) -> Optional[BenchmarkMetadata]:
    """
    Get metadata for a benchmark code.
    
    Args:
        benchmark_code: Unique benchmark identifier
        
    Returns:
        Benchmark metadata or None if not found
    """
    return _benchmark_metadata.get(benchmark_code)


# Decorator for registering generator classes
def generator(benchmark_code: str):
    """Decorator to register a generator class."""
    def decorator(cls):
        register_generator(benchmark_code, cls)
        return cls
    return decorator


# Decorator for registering runner classes
def runner(benchmark_code: str):
    """Decorator to register a runner class."""
    def decorator(cls):
        register_runner(benchmark_code, cls)
        return cls
    return decorator


# Decorator for initializing a benchmark (metadata, generator, runner)
def benchmark(code: str, name: str, description: Optional[str] = None):
    """
    Decorator to initialize a benchmark.
    
    This should be used on the module that contains both generator and runner.
    
    Args:
        code: Unique benchmark identifier
        name: Display name
        description: Optional description
    """
    def decorator(module):
        metadata = BenchmarkMetadata(
            code=code,
            name=name,
            description=description or module.__doc__
        )
        register_benchmark_metadata(metadata)
        return module
    return decorator
