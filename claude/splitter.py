#!/usr/bin/env python3

""" Generates a .pyh.py, .pyconst.py or .docstrings.yaml file from a Python file.

Used for minimizing tokens uploaded as context to an LLM."""

import ast
import yaml
import argparse
import textwrap
from typing import Dict, List, Tuple, Any
from pathlib import Path


def extract_docstrings(source, tree: ast.AST) -> Dict[str, Any]:
    """Extract docstrings from AST into yaml-compatible dict."""
    result = {"module": {"name": "", "doc": ""}}
    
    # Extract module docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        result["module"]["doc"] = module_doc
        
    # Extract functions
    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and isinstance(node.parent, ast.Module):
            func_doc = ast.get_docstring(node)
            if func_doc:
                functions[node.name] = {"doc": func_doc}
    
    if functions:
        result["functions"] = functions
        
    # Extract classes and methods
    classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            class_info = {"doc": class_doc if class_doc else ""}
            
            methods = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_doc = ast.get_docstring(item)
                    if method_doc:
                        methods[item.name] = {"doc": method_doc}
                        
            if methods:
                class_info["methods"] = methods
            classes[node.name] = class_info
            
    if classes:
        result["classes"] = classes
        
    return result


def extract_constants(source, tree: ast.AST) -> List[str]:
    """Extract constant definitions from AST."""
    constants = []
    
    for node in ast.walk(tree):
        # Capture class-level constant dictionaries
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    if all(isinstance(t, ast.Name) for t in item.targets):
                        const_name = item.targets[0].id
                        if const_name.isupper():
                            constants.extend(ast.get_source_segment(source, item).split('\n'))
                            
        # Capture module-level constants
        elif isinstance(node, ast.Assign) and isinstance(node.parent, ast.Module):
            if all(isinstance(t, ast.Name) for t in node.targets):
                const_name = node.targets[0].id
                if const_name.isupper():
                    constants.extend(ast.get_source_segment(source, node).split('\n'))
                    
    return constants

def extract_headers(source, tree: ast.AST) -> List[str]:
    """Extract class and function definitions without implementations."""
    headers = []
    imports = []
    
    def get_complete_def(node: ast.AST) -> str:
        """Get complete function/class definition including type hints."""
        source_lines = source.splitlines()
        start_line = node.lineno - 1
        
        # Handle decorators
        if hasattr(node, 'decorator_list') and node.decorator_list:
            start_line -= len(node.decorator_list)
        
        # Get lines until we find the end of the definition
        def_lines = []
        current_line = start_line
        paren_count = 0
        
        while current_line < len(source_lines):
            line = source_lines[current_line].strip()
            
            # Track parentheses to handle multi-line definitions
            paren_count += line.count('(') - line.count(')')
            
            def_lines.append(line)
            
            # Stop if we're not in parentheses and find a colon
            if paren_count == 0 and ':' in line:
                break
                
            current_line += 1
            
        # Join lines and split at the implementation
        def_str = ' '.join(def_lines)
        # Split at the last colon to handle type hints containing colons
        parts = def_str.rsplit(':', 1)
        return parts[0] + ':'

    # First collect imports
    for node in ast.walk(tree):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            imports.append(ast.get_source_segment(source, node))

    if imports:
        imports.append('')

    # Process definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and isinstance(node.parent, ast.Module):
            for decorator in node.decorator_list:
                headers.append(f"@{ast.get_source_segment(source, decorator)}")
            
            headers.append(get_complete_def(node))
            headers.append("    pass")
            headers.append("")
            
        elif isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                headers.append(f"@{ast.get_source_segment(source, decorator)}")
                
            headers.append(get_complete_def(node))
            
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    for decorator in item.decorator_list:
                        headers.append(f"    @{ast.get_source_segment(source, decorator)}")
                    headers.append(f"    {get_complete_def(item)}")
                    headers.append("        pass")
                    headers.append("")
            
            headers.append("")

    return imports + headers


def extract_implementations(source, tree: ast.AST) -> List[str]:
    """Extract function implementations."""
    implementations = []
    
    # First get any needed imports
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) or isinstance(node, ast.Import):
            if any(name in ast.get_source_segment(source, node) 
                  for name in ['logging', 'logger']):
                implementations.append(ast.get_source_segment(source, node))
                
    implementations.append('\n')
    
    # Then extract all function implementations
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Skip if this is a method
            if not any(isinstance(p, ast.ClassDef) for p in list(ast.walk(node.parent))):
                implementations.append(ast.get_source_segment(source, node))
                implementations.append('\n')
                
        elif isinstance(node, ast.ClassDef):
            # Handle classmethods separately
            class_methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    class_methods.append(f"{node.name}.{item.name} = {item.name}")
                    
            if class_methods:
                implementations.extend(class_methods)
                implementations.append('\n')
                
    return implementations

def get_tree_for_file(input_path: Path):
    """Get the AST for a file."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
        
    # Read source and parse AST
    source = input_path.read_text()
    tree = ast.parse(source)
    
    # Fix parent references
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent

    return source, tree

def generate_docstrings(source, tree, yaml_path):
    docstrings = extract_docstrings(source, tree)
    def str_presenter(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    yaml.add_representer(str, str_presenter)

    # Write YAML with proper newline handling
    yaml_path.write_text(yaml.dump(
      docstrings, sort_keys=False, default_flow_style=False,
      allow_unicode=True))

def process_file(input_path: str) -> None:
    """Process Python file and generate split output files."""
    input_path = Path(input_path)
    source, tree = get_tree_for_file(input_path)
            
    # Generate output files
    stem = input_path.stem
    base_path = input_path.parent
   
    generate_docstrings(source, tree, base_path / f"{stem}.docstrings.yaml")
    
    # Constants
    constants = extract_constants(source, tree)
    const_path = base_path / f"{stem}.pyconst.py"
    const_path.write_text('\n'.join(['#!/usr/bin/python3\n'] + constants))
    
    # Headers
    headers = extract_headers(source, tree)
    header_path = base_path / f"{stem}.pyh.py"
    header_path.write_text('\n'.join(['#!/usr/bin/python3\n'] + headers))
    
    # Implementations
    impls = extract_implementations(source, tree)
    impl_path = base_path / f"{stem}.pyimpl.py"
    impl_path.write_text('\n'.join(['#!/usr/bin/python3\n'] + impls))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Split Python file into components')
    parser.add_argument('input_file', help='Input Python file to process')
    args = parser.parse_args()
    
    try:
        process_file(args.input_file)
    except Exception as e:
        print(f"Error processing file: {e}")
