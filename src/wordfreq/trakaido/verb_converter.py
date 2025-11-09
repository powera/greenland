#!/usr/bin/env python3

"""
Convert verbs from data/trakaido_wordlists/lang_lt/verbs.py to wireword_export.json format.
This module transforms the verb data with grammatical forms into individual entries
for each verb, following the levels.py configuration.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
GREENLAND_REPO_ROOT = os.path.abspath(os.path.join(GREENLAND_SRC_PATH, '..'))
sys.path.append(GREENLAND_SRC_PATH)

# Add the data directory to the path for imports
sys.path.append(os.path.join(GREENLAND_REPO_ROOT, 'data', 'trakaido_wordlists', 'lang_lt'))

try:
    from verbs import verbs_new
    from levels import levels
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure verbs.py and levels.py exist in data/trakaido_wordlists/lang_lt/")
    sys.exit(1)

# Mapping of verb infinitives to groups (based on semantic categories)
VERB_GROUPS = {
    # Basic Needs & Daily Life
    "valgyti": "Basic Needs & Daily Life",
    "gyventi": "Basic Needs & Daily Life", 
    "dirbti": "Basic Needs & Daily Life",
    "gerti": "Basic Needs & Daily Life",
    "miegoti": "Basic Needs & Daily Life",
    "žaisti": "Basic Needs & Daily Life",
    
    # Learning & Knowledge
    "mokytis": "Learning & Knowledge",
    "mokyti": "Learning & Knowledge",
    "skaityti": "Learning & Knowledge",
    "rašyti": "Learning & Knowledge",
    "žinoti": "Learning & Knowledge",
    
    # Actions & Transactions
    "būti": "Actions & Transactions",
    "turėti": "Actions & Transactions",
    "gaminti": "Actions & Transactions",
    "pirkti": "Actions & Transactions",
    "duoti": "Actions & Transactions",
    "imti": "Actions & Transactions",
    
    # Mental & Emotional
    "mėgti": "Mental & Emotional",
    "norėti": "Mental & Emotional",
    "galėti": "Mental & Emotional",
    "kalbėti": "Mental & Emotional",
    
    # Sensory Perception
    "klausyti": "Sensory Perception",
    "matyti": "Sensory Perception",
    
    # Movement & Travel
    "eiti": "Movement & Travel",
    "važiuoti": "Movement & Travel",
    "bėgti": "Movement & Travel",
    "vykti": "Movement & Travel",
    "ateiti": "Movement & Travel",
    "grįžti": "Movement & Travel",
}

def get_level_for_group_and_tense(group_name: str, tense: str) -> Optional[int]:
    """Get the appropriate level for a group and tense combination."""
    
    # Map tense to corpus type
    corpus_mapping = {
        'present_tense': 'verbs_present',
        'past_tense': 'verbs_past', 
        'future': 'verbs_future'
    }
    
    corpus = corpus_mapping.get(tense)
    if not corpus:
        return None
    
    # Search through levels to find matching group and corpus
    for level_name, level_config in levels.items():
        level_num = int(level_name.split('_')[1])
        for config in level_config:
            if (config.get('corpus') == corpus and 
                config.get('group') == group_name):
                return level_num
    
    return None

def convert_person_format(person_key: str) -> str:
    """Convert person format from verbs.py to wireword format.

    Now uses the same format as the Word/Stats API (1s, 3s-m, etc.)
    instead of the old format (1sg, 3sg_m, etc.)
    """
    # Person format is already in the correct format (1s, 3s-m, etc.)
    # No conversion needed
    return person_key

def convert_tense_format(tense_key: str) -> str:
    """Convert tense format from verbs.py to wireword format."""
    mapping = {
        'present_tense': 'pres',
        'past_tense': 'past',
        'future': 'fut'
    }
    return mapping.get(tense_key, tense_key)

def generate_guid(verb_infinitive: str, index: int) -> str:
    """Generate a GUID for the verb."""
    # Create a simple GUID based on index
    return f"V01_{index:03d}"

def convert_verbs_to_wireword_format() -> List[Dict]:
    """Convert verbs from verbs.py to wireword_export.json format."""
    converted_entries = []
    
    # Sort verbs for consistent ordering
    sorted_verbs = sorted(verbs_new.items())
    
    for index, (verb_infinitive, verb_data) in enumerate(sorted_verbs, 1):
        base_english = verb_data['english']
        
        # Get the group for this verb
        group = VERB_GROUPS.get(verb_infinitive)
        if not group:
            print(f"Warning: No group mapping for verb '{verb_infinitive}', skipping...")
            continue
        
        # Determine the level for this verb based on its group
        # We'll use the present tense level as the base level for the verb
        base_level = get_level_for_group_and_tense(group, 'present_tense')
        if base_level is None:
            # If no present tense level, try other tenses
            for tense in ['past_tense', 'future']:
                base_level = get_level_for_group_and_tense(group, tense)
                if base_level is not None:
                    break
        
        if base_level is None:
            print(f"Warning: No level mapping for verb '{verb_infinitive}' in group '{group}', skipping...")
            continue
        
        # Convert the grammatical forms to the new format
        converted_forms = {}
        
        for tense_key, tense_data in verb_data.items():
            if tense_key == 'english':
                continue  # Skip the english translation field
                
            # Get the appropriate level for this specific tense
            form_level = get_level_for_group_and_tense(group, tense_key)
            if form_level is None:
                print(f"Warning: No level mapping for tense '{tense_key}' in group '{group}' for verb '{verb_infinitive}', skipping tense...")
                continue
            
            # Convert tense format
            wireword_tense = convert_tense_format(tense_key)
            
            for person_key, person_data in tense_data.items():
                # Convert person format
                wireword_person = convert_person_format(person_key)
                
                # Create the form key in wireword format
                form_key = f"{wireword_person}_{wireword_tense}"
                
                # Add the form with level information
                converted_forms[form_key] = {
                    "level": form_level,
                    "target": person_data['lithuanian'],
                    "english": person_data['english']
                }
        
        # Generate GUID
        guid = generate_guid(verb_infinitive, index)
        
        # Create basic tags
        tags = [f"level_{base_level}"]
        
        # Add semantic tags based on group
        if group == "Basic Needs & Daily Life":
            tags.extend(["basic_needs", "daily_life", "essential"])
        elif group == "Learning & Knowledge":
            tags.extend(["learning", "knowledge", "education"])
        elif group == "Actions & Transactions":
            tags.extend(["action", "transaction"])
        elif group == "Mental & Emotional":
            tags.extend(["mental", "emotional", "psychological"])
        elif group == "Sensory Perception":
            tags.extend(["sensory", "perception"])
        elif group == "Movement & Travel":
            tags.extend(["movement", "travel", "motion"])
        
        # Add special tags for specific verbs
        if verb_infinitive == "būti":
            tags.extend(["essential", "copula", "irregular"])
        elif verb_infinitive == "turėti":
            tags.extend(["essential", "possession", "auxiliary"])
        elif verb_infinitive in ["galėti", "norėti"]:
            tags.append("modal")
        
        # Create the entry for this verb
        entry = {
            "guid": guid,
            "base_target": verb_infinitive,
            "base_english": base_english,
            "corpus": "VERBS",
            "group": group,
            "level": base_level,
            "word_type": "verb",
            "grammatical_forms": converted_forms,
            "tags": tags
        }
        
        converted_entries.append(entry)
    
    return converted_entries

def export_wireword_verbs(output_path: str = None) -> Tuple[bool, Dict]:
    """
    Export verbs to wireword format.
    
    Args:
        output_path: Path to save the JSON file. If None, uses default path.
        
    Returns:
        Tuple of (success, results_dict)
    """
    try:
        if output_path is None:
            output_path = os.path.join(GREENLAND_REPO_ROOT, 'wireword_verbs_export.json')
        
        # Convert verbs
        converted_entries = convert_verbs_to_wireword_format()
        
        if not converted_entries:
            return False, {"error": "No verbs were converted"}
        
        # Sort by level, then by group, then by GUID for consistent ordering
        converted_entries.sort(key=lambda x: (x['level'], x['group'], x['guid']))
        
        # Save to JSON file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(converted_entries, f, ensure_ascii=False, indent=2)
        
        # Calculate statistics
        level_counts = {}
        group_counts = {}
        total_forms = 0
        tense_form_counts = {}
        
        for entry in converted_entries:
            level = entry['level']
            level_counts[level] = level_counts.get(level, 0) + 1
            
            group = entry['group']
            group_counts[group] = group_counts.get(group, 0) + 1
            
            # Count grammatical forms
            for form_key in entry['grammatical_forms']:
                total_forms += 1
                if '_' in form_key:
                    tense = form_key.split('_')[-1]  # Get the last part (tense)
                    tense_form_counts[tense] = tense_form_counts.get(tense, 0) + 1
        
        # Check for skipped verbs
        all_verbs = set(verbs_new.keys())
        converted_verbs = {entry['base_lithuanian'] for entry in converted_entries}
        skipped_verbs = all_verbs - converted_verbs
        
        results = {
            "output_path": str(output_path),
            "total_verbs": len(converted_entries),
            "total_forms": total_forms,
            "levels": sorted(level_counts.keys()),
            "level_distribution": dict(sorted(level_counts.items())),
            "tense_form_distribution": tense_form_counts,
            "group_distribution": dict(sorted(group_counts.items())),
            "skipped_verbs": sorted(skipped_verbs) if skipped_verbs else []
        }
        
        return True, results
        
    except Exception as e:
        return False, {"error": str(e)}

def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert verbs to wireword format")
    parser.add_argument('--output', '-o', help='Output JSON file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("Converting verbs from verbs.py to wireword_export.json format...")
    
    success, results = export_wireword_verbs(args.output)
    
    if success:
        print(f"✅ Conversion completed successfully!")
        print(f"   Output file: {results['output_path']}")
        print(f"   Total verbs: {results['total_verbs']}")
        print(f"   Total grammatical forms: {results['total_forms']}")
        print(f"   Levels: {results['levels']}")
        
        if args.verbose:
            print(f"   Level distribution: {results['level_distribution']}")
            print(f"   Tense form distribution: {results['tense_form_distribution']}")
            print(f"   Group distribution: {results['group_distribution']}")
            
            if results['skipped_verbs']:
                print(f"   Skipped verbs ({len(results['skipped_verbs'])}): {', '.join(results['skipped_verbs'])}")
    else:
        print(f"❌ Conversion failed: {results.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()