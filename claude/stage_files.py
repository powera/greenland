#!/usr/bin/env python3
"""
Tool for preparing project files for Claude integration.
Creates directory with flattened core files and full file listing.
"""

import os
import yaml
import shutil
import subprocess
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from splitter import get_tree_for_file, extract_headers

@dataclass
class FileConfig:
    """Configuration for a file to be staged."""
    path: str
    description: str = ""
    header_only: bool = False

def load_file_config(config_path: Path) -> Dict[str, List[FileConfig]]:
    """
    Load file configuration from YAML.
    
    :param config_path: Path to YAML configuration file
    :return: Dictionary of section names to file configurations
    :raises: FileNotFoundError, yaml.YAMLError
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with config_path.open() as f:
        config = yaml.safe_load(f)
        
    sections = {}
    for section_name, file_list in config.items():
        sections[section_name] = [
            FileConfig(
                path=item['path'],
                description=item.get('description', ''),
                header_only=item.get('header_only', False)
            )
            for item in file_list
        ]
    
    return sections

def ensure_clean_dir(directory: Path) -> None:
    """Create empty directory, removing old contents if necessary."""
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()

def get_flat_filename(filepath: str) -> str:
    """
    Convert path to flat filename, using prefix for disambiguation.
    Removes 'src' prefix if present.
    
    Examples:
        src/common/auth.py -> common__auth.py
        migrations/env.py -> migrations__env.py
        src/constants.py -> constants.py
    """
    path = Path(filepath)
    parts = list(path.parts)
    
    # Remove 'src' if it's the first component
    if parts[0] == 'src':
        parts.pop(0)
        
    # If only filename remains, return it
    if len(parts) == 1:
        return parts[0]
        
    # Otherwise join all parts except filename with __, then add filename
    prefix = '__'.join(parts[:-1])
    return f"{prefix}__{parts[-1]}"

def check_name_collisions(configs: List[FileConfig]) -> Dict[str, str]:
    """
    Check for filename collisions and return mapping of original paths to flat names.
    
    :param configs: List of file configurations to check
    :return: Dictionary mapping original paths to flat filenames
    """
    # Map each path to its flat name
    path_to_name = {config.path: get_flat_filename(config.path) for config in configs}
    
    # Verify no collisions in the flat names
    used_names = defaultdict(list)
    for path, name in path_to_name.items():
        used_names[name].append(path)
        
    # Report any collisions found
    for name, paths in used_names.items():
        if len(paths) > 1:
            print(f"Warning: Name collision for {name}:")
            for path in paths:
                print(f"  {path}")
                
    return path_to_name

def get_project_files() -> str:
    """Get list of all tracked files in the git repository."""
    try:
        result = subprocess.run(
            ['git', 'ls-tree', '-r', '--name-only', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}")
        return ""
    except FileNotFoundError:
        print("Error: git command not found")
        return ""

def process_file(src_path: Path, dest_path: Path, header_only: bool = False) -> bool:
    """
    Process a single file, either copying it entirely or extracting headers.
    
    :param src_path: Source file path
    :param dest_path: Destination file path
    :param header_only: If True, extract only headers
    :return: True if successful, False otherwise
    """
    try:
        if header_only:
            source, tree = get_tree_for_file(src_path)
            headers = extract_headers(source, tree)
            content = '\n'.join(['#!/usr/bin/python3\n'] + headers)
            dest_path.write_text(content)
            print(f"Extracted headers: {src_path} -> {dest_path}")
        else:
            shutil.copy2(src_path, dest_path)
            print(f"Copied: {src_path} -> {dest_path}")
        return True
    except Exception as e:
        print(f"Error processing {src_path}: {str(e)}")
        return False

def update_claude_core() -> None:
    """Update claude_core directory with flattened files and file listing."""
    claude_core = Path.cwd() / 'claude' / 'staging'
    config_path = Path.cwd() / 'claude' / 'config.yaml'
    
    try:
        # Load configuration
        sections = load_file_config(config_path)
        
        # Combine all file configs for collision checking
        all_configs = []
        for section_configs in sections.values():
            all_configs.extend(section_configs)
            
        # Ensure clean staging directory
        ensure_clean_dir(claude_core)
        
        # Check for name collisions
        path_to_name = check_name_collisions(all_configs)
        
        # Process all files
        processed = 0
        for section_name, configs in sections.items():
            print(f"\nProcessing {section_name}:")
            for config in configs:
                src_path = Path.cwd() / config.path
                if not src_path.exists():
                    print(f"Warning: File not found: {config.path}")
                    continue
                    
                flat_name = path_to_name[config.path]
                # Modify suffix for header-only Python files
                if config.header_only and flat_name.endswith('.py'):
                    flat_name = flat_name[:-3] + '.pyh.py'
                dest_path = claude_core / flat_name
                
                if process_file(src_path, dest_path, config.header_only):
                    processed += 1
        
        # Create file listing
        file_list = get_project_files()
        if file_list:
            list_path = claude_core / 'project_files.txt'
            list_path.write_text(file_list)
            print(f"\nCreated file listing: {list_path}")
        
        print(f"\nSuccessfully processed {processed} files to {claude_core}")
        
    except Exception as e:
        print(f"Error updating claude core: {str(e)}")
        raise

if __name__ == '__main__':
    update_claude_core()
