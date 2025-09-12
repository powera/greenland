
#!/usr/bin/env python3
"""
Text rendering and formatting utilities for trakaido tools.

Provides reusable functions for displaying word data, statistics, and other
text-based output in a consistent format.
"""

from typing import Dict, Any, List
from dataclasses import dataclass


def format_subtype_display_name(subtype: str) -> str:
    """
    Convert database subtype values to display-friendly names.
    
    Args:
        subtype: Raw subtype value from database
        
    Returns:
        Display-friendly subtype name
    """
    # Handle None or empty values
    if not subtype:
        return "Other"
    
    # Special cases that need custom formatting
    special_cases = {
        # Noun subtypes
        "animal": "Animals",
        "food_drink": "Food/Drink",
        "small_movable_object": "Small Movable Object",
        "clothing_accessory": "Clothing/Accessory",
        "building_structure": "Building/Structure",
        "artwork_artifact": "Artwork/Artifact",
        "tool_machine": "Tool/Machine",
        "path_infrastructure": "Path/Infrastructure",
        "material_substance": "Material/Substance",
        "chemical_compound": "Chemical Compound",
        "medication_remedy": "Medication/Remedy",
        "concept_idea": "Concept/Idea",
        "symbolic_element": "Symbolic Element",
        "quality_attribute": "Quality/Attribute",
        "mental_construct": "Mental Construct",
        "knowledge_domain": "Knowledge Domain",
        "quantitative_concept": "Quantitative Concept",
        "emotion_feeling": "Emotion/Feeling",
        "process_event": "Process/Event",
        "time_period": "Time Period",
        "group_people": "Group of People",
        "animal_grouping_term": "Animal Grouping",
        "collection_things": "Collection of Things",
        "personal_name": "Personal Name",
        "place_name": "Place Name",
        "organization_name": "Organization Name",
        "temporal_name": "Temporal Name",
        "unit_of_measurement": "Unit of Measurement",
        "body_part": "Body Part",
        "natural_feature": "Natural Feature", 
        "disease_condition": "Disease/Condition",
        "human": "Humans",
        "plant": "Plants",
        
        # Verb subtypes
        "physical_action": "Physical Action",
        "creation_action": "Creation Action",
        "destruction_action": "Destruction Action",
        "mental_state": "Mental State",
        "emotional_state": "Emotional State",
        "directional_movement": "Directional Movement",
        "manner_movement": "Manner Movement",
        
        # Adjective subtypes
        "definite_quantity": "Definite Quantity",
        "indefinite_quantity": "Indefinite Quantity",
        
        # Adverb subtypes
        "specific_time": "Specific Time",
        "relative_time": "Relative Time",
        "definite_frequency": "Definite Frequency",
        "indefinite_frequency": "Indefinite Frequency",
    }
    
    # Check for special cases first
    if subtype in special_cases:
        return special_cases[subtype]
    
    # For regular cases, convert underscores to spaces and title case
    formatted = subtype.replace("_", " ")
    
    # Default: title case each word
    return formatted.title()


def display_word_data(word_data) -> None:
    """
    Display word data in a formatted table for user review.
    
    Args:
        word_data: WordData object with word information
    """
    print("\n" + "="*60)
    print("WORD ANALYSIS RESULTS")
    print("="*60)
    print(f"English: {word_data.english}")
    print(f"Lithuanian: {word_data.lithuanian}")
    print(f"Part of Speech: {word_data.pos_type}")
    print(f"Subtype: {word_data.pos_subtype}")
    print(f"Definition: {word_data.definition}")
    print(f"Confidence: {word_data.confidence:.2f}")

    # Show additional translations
    translations = []
    if word_data.chinese_translation:
        translations.append(f"Chinese: {word_data.chinese_translation}")
    if word_data.korean_translation:
        translations.append(f"Korean: {word_data.korean_translation}")
    if word_data.french_translation:
        translations.append(f"French: {word_data.french_translation}")
    if word_data.swahili_translation:
        translations.append(f"Swahili: {word_data.swahili_translation}")
    if word_data.vietnamese_translation:
        translations.append(f"Vietnamese: {word_data.vietnamese_translation}")

    if translations:
        print("Other translations:")
        for trans in translations:
            print(f"  {trans}")

    if word_data.alternatives['english']:
        print(f"English Alternatives: {', '.join(word_data.alternatives['english'])}")
    if word_data.alternatives['lithuanian']:
        print(f"Lithuanian Alternatives: {', '.join(word_data.alternatives['lithuanian'])}")

    if word_data.notes:
        print(f"Notes: {word_data.notes}")
    print("="*60)


def display_current_lemma_entry(lemma) -> None:
    """
    Display current lemma entry information in a formatted table.
    
    Args:
        lemma: Lemma object from database
    """
    print("\n" + "="*60)
    print("CURRENT ENTRY:")
    print("="*60)
    print(f"English: {lemma.lemma_text}")
    print(f"Lithuanian: {lemma.lithuanian_translation}")
    print(f"Part of Speech: {lemma.pos_type}")
    print(f"Subtype: {lemma.pos_subtype}")
    print(f"Definition: {lemma.definition_text}")
    print(f"Level: {lemma.difficulty_level}")
    print(f"Chinese: {lemma.chinese_translation or 'N/A'}")
    print(f"Korean: {lemma.korean_translation or 'N/A'}")
    print(f"French: {lemma.french_translation or 'N/A'}")
    print(f"Swahili: {lemma.swahili_translation or 'N/A'}")
    print(f"Vietnamese: {lemma.vietnamese_translation or 'N/A'}")
    print(f"Notes: {lemma.notes or 'N/A'}")
    print("="*60)


def display_word_list(words: List[Dict[str, Any]], title: str = "Words") -> None:
    """
    Display a list of words in a formatted table.
    
    Args:
        words: List of word dictionaries
        title: Title for the word list
    """
    if words:
        print(f"\n{title} ({len(words)} found):")
        print("-" * 80)
        for word in words:
            status = "✓" if word.get('verified', False) else "?"
            print(f"{status} {word.get('guid', ''):<10} L{word.get('level', 0):<2} "
                  f"{word.get('english', ''):<20} → {word.get('lithuanian', ''):<20} "
                  f"({word.get('subtype', '')})")
    else:
        print(f"No {title.lower()} found matching criteria.")


def display_subtype_list(subtypes: List[Dict[str, Any]]) -> None:
    """
    Display a list of subtypes with counts in a formatted table.
    
    Args:
        subtypes: List of subtype dictionaries with count information
    """
    if subtypes:
        print(f"\nFound {len(subtypes)} subtypes:")
        print("-" * 60)
        for subtype_info in subtypes:
            print(f"{subtype_info['pos_subtype']:<25} ({subtype_info['pos_type']:<10}) {subtype_info['count']:>6} words")
    else:
        print("No subtypes found.")


def display_export_summary(export_type: str, success: bool, stats=None, **kwargs) -> None:
    """
    Display a summary of export operation results.
    
    Args:
        export_type: Type of export performed
        success: Whether export was successful
        stats: Export statistics object (optional)
        **kwargs: Additional information to display
    """
    if success:
        print(f"\n✅ {export_type} export completed successfully!")
        
        if stats:
            print(f"   Total entries: {stats.total_entries}")
            if hasattr(stats, 'entries_with_guids'):
                print(f"   Entries with GUIDs: {stats.entries_with_guids}")
            if hasattr(stats, 'pos_distribution'):
                print(f"   POS distribution: {stats.pos_distribution}")
            if hasattr(stats, 'level_distribution'):
                print(f"   Level distribution: {stats.level_distribution}")
        
        # Display additional information from kwargs
        for key, value in kwargs.items():
            print(f"   {key.replace('_', ' ').title()}: {value}")
    else:
        print(f"\n❌ {export_type} export failed")


def display_bulk_operation_preview(items: List[Any], operation: str, details: str = "") -> None:
    """
    Display a preview of items that will be affected by a bulk operation.
    
    Args:
        items: List of items to display
        operation: Description of the operation
        details: Additional details about the operation
    """
    print(f"Found {len(items)} items for {operation}:")
    if details:
        print(f"Details: {details}")
    print("-" * 80)

    for item in items:
        if hasattr(item, 'guid'):
            # Display lemma/word items
            status = "✓" if getattr(item, 'verified', False) else "?"
            print(f"{status} {item.guid:<10} L{getattr(item, 'difficulty_level', 0):<2} "
                  f"{getattr(item, 'lemma_text', ''):<20} → {getattr(item, 'lithuanian_translation', '') or 'N/A':<20}")
        else:
            # Display generic items
            print(f"   {item}")


def format_change_summary(changes: List[str]) -> str:
    """
    Format a list of changes into a readable summary.
    
    Args:
        changes: List of change descriptions
        
    Returns:
        Formatted change summary string
    """
    if not changes:
        return "No changes detected"
    
    summary = "Changes made:\n"
    for change in changes:
        summary += f"   {change}\n"
    
    return summary.strip()


def get_user_confirmation(message: str, default: bool = False) -> bool:
    """
    Get user confirmation for an operation.
    
    Args:
        message: Message to display to user
        default: Default value if user just presses enter
        
    Returns:
        True if user confirms, False otherwise
    """
    default_suffix = " (Y/n)" if default else " (y/N)"
    response = input(f"{message}{default_suffix}: ").strip().lower()
    
    if not response:
        return default
    
    return response in ['y', 'yes', 'true', '1']


def display_progress(current: int, total: int, item_name: str = "") -> None:
    """
    Display progress for long-running operations.
    
    Args:
        current: Current item number
        total: Total number of items
        item_name: Name of current item being processed
    """
    percentage = (current / total) * 100 if total > 0 else 0
    progress_bar = "█" * int(percentage // 5) + "░" * (20 - int(percentage // 5))
    
    print(f"\r[{current}/{total}] [{progress_bar}] {percentage:.1f}% {item_name}", end='', flush=True)
    
    if current == total:
        print()  # New line when complete
