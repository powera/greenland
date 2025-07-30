#!/usr/bin/env python3
"""
Convert Anki notes.txt file to simplified JSON format.

Extracts only the essential fields:
- id: The note ID
- text: The flashcard content (flds field with Unit Separators parsed)
- key: The sort field key (sfld)
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any


def parse_anki_line(line: str) -> Dict[str, Any]:
    """Parse a single line from the Anki notes file."""
    line = line.strip()
    
    try:
        # Structure: id|guid|mid|mod|usn|tags|flds|word|sfld|flags|data
        # The challenge is that GUID can contain pipe characters
        # We'll parse by finding the numeric fields that we know the positions of
        
        # Find the first pipe (after ID)
        first_pipe = line.find('|')
        if first_pipe == -1:
            raise ValueError("No pipe separator found")
        
        note_id = int(line[:first_pipe])
        
        # Work backwards from the end to find the known numeric fields
        # Last field is data (can be anything), second-to-last is flags (numeric),
        # third-to-last is sfld (numeric), fourth-to-last is word (text)
        parts = line.split('|')
        
        # We need at least: id|guid|mid|mod|usn|tags|flds|word|sfld|flags|data (11 parts minimum)
        if len(parts) < 11:
            raise ValueError(f"Not enough fields: expected at least 11, got {len(parts)}")
        
        # Work backwards to find the structure
        data = parts[-1]                    # Last field
        flags = int(parts[-2])              # Second to last (numeric)
        sfld = int(parts[-3])               # Third to last (numeric)  
        word = parts[-4]                    # Fourth to last (word)
        
        # Now we need to find where flds ends and word begins
        # We'll reconstruct by finding the pattern: |numeric|numeric|numeric|text|flds_content|word|sfld|flags|data
        
        # Find the three consecutive numeric fields (mid|mod|usn) after the GUID
        remaining = line[first_pipe + 1:]  # Everything after the first pipe
        
        # Try different positions for where the GUID ends
        for i in range(len(parts) - 10):  # Leave room for mid|mod|usn|tags|flds|word|sfld|flags|data
            try:
                # Try to parse three consecutive numbers starting at position i+1
                if i == 0:
                    # GUID is just parts[1]
                    guid = parts[1]
                    mid = int(parts[2])
                    mod = int(parts[3])
                    usn = int(parts[4])
                    tags = parts[5]
                    # flds is everything from parts[6] to parts[-4]
                    flds_parts = parts[6:-4]
                    flds_content = '|'.join(flds_parts)
                else:
                    # GUID spans multiple parts due to embedded pipes
                    guid = '|'.join(parts[1:i+2])
                    mid = int(parts[i+2])
                    mod = int(parts[i+3])
                    usn = int(parts[i+4])
                    tags = parts[i+5]
                    # flds is everything from parts[i+6] to parts[-4]
                    flds_parts = parts[i+6:-4]
                    flds_content = '|'.join(flds_parts)
                
                # If we got here without exception, we found the right split
                break
                
            except (ValueError, IndexError):
                continue
        else:
            raise ValueError("Could not parse field structure")
        
        # Parse the flds content (split by Unit Separator \x1f)
        text_parts = flds_content.split('\x1f')
        
        # Extract word from the first part of flds
        word_from_flds = text_parts[0] if len(text_parts) > 0 else ""
        
        # Create a simplified structure with parsed fields
        note = {
            "id": note_id,
            "text": {
                "word": word_from_flds,
                "definition": text_parts[1] if len(text_parts) > 1 else "",
                "synonyms": text_parts[2] if len(text_parts) > 2 else "",
                "example": text_parts[3] if len(text_parts) > 3 else "",
                "part_of_speech": text_parts[4] if len(text_parts) > 4 else "",
                "raw_content": flds_content  # Keep the original for reference
            },
            "key": sfld
        }
        
        return note
        
    except (ValueError, IndexError) as e:
        raise ValueError(f"Error parsing line: {e}")


def convert_notes_to_json(input_file: str, output_file: str = None) -> List[Dict[str, Any]]:
    """
    Convert Anki notes.txt file to simplified JSON format.
    
    Args:
        input_file: Path to the input notes.txt file
        output_file: Optional path to output JSON file. If None, prints to stdout.
    
    Returns:
        List of simplified note dictionaries
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    notes = []
    
    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():  # Skip empty lines
                try:
                    note = parse_anki_line(line)
                    notes.append(note)
                except ValueError as e:
                    print(f"Warning: Skipping line {line_num}: {e}", file=sys.stderr)
                    continue
    
    # Output results
    json_output = json.dumps(notes, indent=2, ensure_ascii=False)
    
    if output_file:
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f"Converted {len(notes)} notes to {output_file}")
    else:
        print(json_output)
    
    return notes


def main():
    """Main function to handle command line usage."""
    if len(sys.argv) < 2:
        print("Usage: python convert_notes_to_json.py <input_file> [output_file]")
        print("Example: python convert_notes_to_json.py data/gre_words/notes.txt notes.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        convert_notes_to_json(input_file, output_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()