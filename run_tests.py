#!/usr/bin/python3

import unittest
import sys
import os
from typing import List, Optional

def discover_test_directories() -> List[str]:
    """
    Find all directories that might contain test files.
    Walks through project directories looking for Python files starting with 'test_'.
    """
    test_dirs = set()
    project_root = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(project_root, 'src')
    
    for root, _, files in os.walk(src_dir):
        if any(f.startswith('test_') and f.endswith('.py') for f in files):
            # Get relative path from src directory
            rel_path = os.path.relpath(root, src_dir)
            test_dirs.add(rel_path if rel_path != '.' else '')
    
    return sorted(test_dirs)

def run_test_suite(test_dirs: Optional[List[str]] = None) -> bool:
    """
    Run all discovered tests and return whether all tests passed.
    
    Args:
        test_dirs: Optional list of directories to search for tests.
                  If None, will discover all test directories.
    
    Returns:
        bool: True if all tests passed, False otherwise
    """
    if test_dirs is None:
        test_dirs = discover_test_directories()
    
    # Get absolute paths
    project_root = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(project_root, 'src')
    
    # Add src directory to Python path for imports
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    
    # Create test loader
    loader = unittest.TestLoader()
    
    # Discover and load tests from each directory
    suite = unittest.TestSuite()
    for test_dir in test_dirs:
        # Get absolute path for test directory
        abs_test_dir = os.path.join(src_dir, test_dir)
        
        # Discover tests in this directory
        tests = loader.discover(abs_test_dir, pattern='test_*.py', top_level_dir=src_dir)
        suite.addTests(tests)
    
    # Run the test suite
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    # Allow specific test directories to be passed as arguments
    test_dirs = sys.argv[1:] if len(sys.argv) > 1 else None
    
    success = run_test_suite(test_dirs)
    sys.exit(0 if success else 1)
