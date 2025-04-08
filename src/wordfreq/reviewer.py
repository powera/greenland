#!/usr/bin/python3

"""Interactive tool for reviewing and updating linguistic data."""

import logging
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import constants
from wordfreq import linguistic_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class CliColors:
    """ANSI color codes for CLI formatting."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class LinguisticReviewer:
    """Interactive tool for reviewing and updating linguistic data."""
    
    def __init__(self, db_path: str = constants.WORDFREQ_DB_PATH):
        """
        Initialize reviewer with database session.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.session = linguistic_db.create_database_session(db_path)
        logger.info(f"Connected to database: {db_path}")
        
        # Set up CLI colors
        self.c = CliColors()
    
    def display_word_info(self, word_text: str) -> bool:
        """
        Display information about a word.
        
        Args:
            word_text: Word to display
            
        Returns:
            Whether the word exists in the database
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        print(f"\n{self.c.HEADER}{self.c.BOLD}Word:{self.c.ENDC} {word.word}")
        print(f"{self.c.BLUE}Rank:{self.c.ENDC} {word.frequency_rank}")
        
        # Definitions
        definitions = word.definitions
        print(f"\n{self.c.HEADER}Definitions:{self.c.ENDC}")
        if not definitions:
            print(f"  {self.c.YELLOW}No definitions recorded{self.c.ENDC}")
        else:
            for i, definition in enumerate(definitions):
                flags = []
                if definition.multiple_meanings:
                    flags.append("multiple meanings")
                if definition.special_case:
                    flags.append("special case")
                
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                verified_str = f" {self.c.GREEN}[✓]{self.c.ENDC}" if definition.verified else ""
                
                print(f"  {self.c.CYAN}[{i+1}]{self.c.ENDC} {definition.definition_text}{flag_str}{verified_str}")
                print(f"    {self.c.BLUE}Confidence:{self.c.ENDC} {definition.confidence:.2f}")
                print(f"    {self.c.BLUE}Part of speech:{self.c.ENDC} {definition.pos_type}")
                print(f"    {self.c.BLUE}Lemma:{self.c.ENDC} {definition.lemma}")
                if definition.chinese_translation:
                    print(f"    {self.c.BLUE}Chinese:{self.c.ENDC} {definition.chinese_translation}")
                if definition.pos_subtype:
                    print(f"    {self.c.BLUE}Subtype:{self.c.ENDC} {definition.pos_subtype}")

                if definition.notes:
                    print(f"    {self.c.BLUE}Notes:{self.c.ENDC} {definition.notes}")
                
                # Examples
                examples = definition.examples
                if examples:
                    print(f"    {self.c.BLUE}Examples:{self.c.ENDC}")
                    for j, example in enumerate(examples):
                        print(f"      - {example.example_text}")
                
                # Add a separator between definitions
                if i < len(definitions) - 1:
                    print()
        
        return True
        
    def edit_definition(self, word_text: str) -> bool:
        """
        Edit a definition for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the edit was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current definitions
        self.display_word_info(word_text)
        
        # Choose definition to edit
        definitions = word.definitions
        if not definitions:
            print(f"{self.c.YELLOW}No definitions to edit. Add one first.{self.c.ENDC}")
            return False
        
        try:
            choice = int(input(f"\n{self.c.BOLD}Enter definition number to edit (1-{len(definitions)}) or 0 to cancel: {self.c.ENDC}"))
            if choice == 0:
                return False
            
            if choice < 1 or choice > len(definitions):
                print(f"{self.c.RED}Invalid choice.{self.c.ENDC}")
                return False
            
            definition = definitions[choice-1]
            
            # Get new values
            print(f"\n{self.c.BOLD}Editing definition #{choice}. Press Enter to keep current values.{self.c.ENDC}")
            
            new_definition_text = input(f"Definition [{definition.definition_text}]: ").strip()
            new_definition_text = new_definition_text if new_definition_text else None
            
            new_pos_type = input(f"Part of speech [{definition.pos_type}]: ").strip()
            new_pos_type = new_pos_type if new_pos_type else None
            
            new_lemma = input(f"Lemma [{definition.lemma}]: ").strip()
            new_lemma = new_lemma if new_lemma else None
            
            new_confidence = input(f"Confidence [{definition.confidence}]: ").strip()
            try:
                new_confidence = float(new_confidence) if new_confidence else None
            except ValueError:
                new_confidence = None
            
            new_multiple = input(f"Multiple meanings (y/n) [{definition.multiple_meanings}]: ").strip().lower()
            if new_multiple in ('y', 'yes'):
                new_multiple = True
            elif new_multiple in ('n', 'no'):
                new_multiple = False
            else:
                new_multiple = None
            
            new_special = input(f"Special case (y/n) [{definition.special_case}]: ").strip().lower()
            if new_special in ('y', 'yes'):
                new_special = True
            elif new_special in ('n', 'no'):
                new_special = False
            else:
                new_special = None
            
            new_verified = input(f"Verified (y/n) [{definition.verified}]: ").strip().lower()
            if new_verified in ('y', 'yes'):
                new_verified = True
            elif new_verified in ('n', 'no'):
                new_verified = False
            else:
                new_verified = None
            
            new_notes = input(f"Notes [{definition.notes or ''}]: ").strip()
            new_notes = new_notes if new_notes else None
            
            # Update definition
            linguistic_db.update_definition(
                self.session,
                definition.id,
                definition_text=new_definition_text,
                pos_type=new_pos_type,
                lemma=new_lemma,
                confidence=new_confidence,
                multiple_meanings=new_multiple,
                special_case=new_special,
                verified=new_verified,
                notes=new_notes
            )
            
            print(f"{self.c.GREEN}Definition updated successfully.{self.c.ENDC}")
            return True
            
        except ValueError:
            print(f"{self.c.RED}Invalid input.{self.c.ENDC}")
            return False
    
    def add_definition(self, word_text: str) -> bool:
        """
        Add a new definition for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the addition was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current definitions
        self.display_word_info(word_text)
        
        # Get new definition values
        print(f"\n{self.c.BOLD}Adding new definition for '{word.word}'.{self.c.ENDC}")
        
        definition_text = input("Definition: ").strip()
        if not definition_text:
            print(f"{self.c.RED}Definition cannot be empty.{self.c.ENDC}")
            return False
        
        pos_type = input("Part of speech: ").strip()
        if not pos_type:
            print(f"{self.c.RED}Part of speech cannot be empty.{self.c.ENDC}")
            return False
        
        lemma = input(f"Lemma [default: {word.word}]: ").strip()
        lemma = lemma if lemma else word.word
        
        confidence_str = input("Confidence (0-1) [1.0]: ").strip()
        try:
            confidence = float(confidence_str) if confidence_str else 1.0
        except ValueError:
            print(f"{self.c.RED}Invalid confidence value.{self.c.ENDC}")
            return False
        
        multiple = input("Multiple meanings (y/n) [n]: ").strip().lower()
        multiple = multiple in ('y', 'yes')
        
        special = input("Special case (y/n) [n]: ").strip().lower()
        special = special in ('y', 'yes')
        
        verified = input("Verified (y/n) [y]: ").strip().lower()
        verified = verified != 'n' and verified != 'no'
        
        notes = input("Notes: ").strip()
        notes = notes if notes else None
        
        # Add definition
        definition = linguistic_db.add_definition(
            self.session,
            word,
            definition_text=definition_text,
            pos_type=pos_type,
            lemma=lemma,
            confidence=confidence,
            multiple_meanings=multiple,
            special_case=special,
            notes=notes
        )
        
        # See if user wants to add examples
        add_examples = input(f"{self.c.BOLD}Would you like to add example sentences? (y/n) [y]: {self.c.ENDC}").strip().lower()
        if add_examples != 'n' and add_examples != 'no':
            while True:
                example_text = input("Example sentence (or leave empty to finish): ").strip()
                if not example_text:
                    break
                
                linguistic_db.add_example(self.session, definition, example_text)
                print(f"{self.c.GREEN}Example added.{self.c.ENDC}")
        
        print(f"{self.c.GREEN}Definition added successfully.{self.c.ENDC}")
        return True
        
    def add_example(self, word_text: str) -> bool:
        """
        Add an example sentence to a definition.
        
        Args:
            word_text: Word containing the definition
            
        Returns:
            Whether the addition was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current definitions
        self.display_word_info(word_text)
        
        # Choose definition to add example to
        definitions = word.definitions
        if not definitions:
            print(f"{self.c.YELLOW}No definitions to add examples to. Add a definition first.{self.c.ENDC}")
            return False
        
        try:
            choice = int(input(f"\n{self.c.BOLD}Enter definition number to add example to (1-{len(definitions)}) or 0 to cancel: {self.c.ENDC}"))
            if choice == 0:
                return False
            
            if choice < 1 or choice > len(definitions):
                print(f"{self.c.RED}Invalid choice.{self.c.ENDC}")
                return False
            
            definition = definitions[choice-1]
            
            # Get example text
            example_text = input("Example sentence: ").strip()
            if not example_text:
                print(f"{self.c.RED}Example cannot be empty.{self.c.ENDC}")
                return False
            
            # Add example
            linguistic_db.add_example(self.session, definition, example_text)
            
            print(f"{self.c.GREEN}Example added successfully.{self.c.ENDC}")
            return True
            
        except ValueError:
            print(f"{self.c.RED}Invalid input.{self.c.ENDC}")
            return False
    
    def list_problematic_words(self, limit: int = 10) -> None:
        """
        List problematic words.
        
        Args:
            limit: Maximum number of words to display
        """
        print(f"\n{self.c.HEADER}{self.c.BOLD}Problematic Words:{self.c.ENDC}")
        
        words = linguistic_db.list_problematic_words(self.session, limit=limit)
        if not words:
            print(f"{self.c.YELLOW}No problematic words found.{self.c.ENDC}")
            return
        
        for item in words:
            # Collect flags from all definitions
            all_flags = []
            for definition in item['definitions']:
                if definition['multiple_meanings']:
                    all_flags.append("multiple meanings")
                if definition['special_case']:
                    all_flags.append("special case")
            
            flag_str = f" [{', '.join(set(all_flags))}]" if all_flags else ""
            
            print(f"{self.c.CYAN}{item['word']}{self.c.ENDC}{flag_str} (rank: {item['rank']})")
            # Show definition summaries
            for i, definition in enumerate(item['definitions']):
                print(f"  {i+1}. {definition['pos']} - {definition['text'][:50]}...")
    
    def list_common_words_by_pos(self, pos_type: str, limit: int = 20) -> None:
        """
        List the most common words for a specified part of speech.
        
        Args:
            pos_type: Part of speech to filter by
            limit: Maximum number of words to display
        """
        print(f"\n{self.c.HEADER}{self.c.BOLD}Most Common {pos_type.capitalize()} Words:{self.c.ENDC}")
        
        words = linguistic_db.get_common_words_by_pos(self.session, pos_type, limit=limit)
        if not words:
            print(f"{self.c.YELLOW}No words found with part of speech '{pos_type}'.{self.c.ENDC}")
            return
        
        # Calculate column widths
        word_width = max(len("Word"), max(len(item["word"]) for item in words))
        lemma_width = max(len("Lemma"), max(len(str(item["lemma"] or "")) for item in words))
        
        # Print header
        header = (
            f"{self.c.BOLD}{'Rank':<6} "
            f"{'Word':<{word_width}} "
            f"{'Lemma':<{lemma_width}} "
            f"{'Confidence':<10} "
            f"{'Definition'}{self.c.ENDC}"
        )
        print(header)
        print("-" * (6 + word_width + lemma_width + 10 + 20))
        
        # Print words
        for item in words:
            # Truncate definition for display
            definition = item['definition'][:50] + "..." if len(item['definition']) > 50 else item['definition']
            
            row = (
                f"{item['rank']:<6} "
                f"{item['word']:<{word_width}} "
                f"{item['lemma'] or '':<{lemma_width}} "
                f"{item['confidence']:<10.2f} "
                f"{definition}"
            )
            print(row)

    def find_missing_data(self, limit: int = 10) -> None:
        """
        Find words with missing linguistic data.
        
        Args:
            limit: Maximum number of words to display
        """
        print(f"\n{self.c.HEADER}{self.c.BOLD}Words with Missing Data:{self.c.ENDC}")
        
        words = linguistic_db.get_words_needing_analysis(self.session, limit=limit)
        if not words:
            print(f"{self.c.GREEN}No words with missing data found.{self.c.ENDC}")
            return
        
        for word in words:
            print(f"{self.c.CYAN}{word.word}{self.c.ENDC} (rank: {word.frequency_rank}) - Missing: definitions")
    
    def interactive_menu(self) -> None:
        """Run interactive menu for reviewing and editing words."""
        while True:
            print(f"\n{self.c.HEADER}{self.c.BOLD}Linguistic Data Reviewer{self.c.ENDC}")
            print(f"{self.c.CYAN}1.{self.c.ENDC} Display word information")
            print(f"{self.c.CYAN}2.{self.c.ENDC} Edit definition")
            print(f"{self.c.CYAN}3.{self.c.ENDC} Add definition")
            print(f"{self.c.CYAN}4.{self.c.ENDC} Add example to definition")
            print(f"{self.c.CYAN}5.{self.c.ENDC} List problematic words")
            print(f"{self.c.CYAN}6.{self.c.ENDC} Find words with missing data")
            print(f"{self.c.CYAN}7.{self.c.ENDC} Show statistics")
            print(f"{self.c.CYAN}8.{self.c.ENDC} List common words by part of speech")
            print(f"{self.c.CYAN}9.{self.c.ENDC} Data migration tools")

            print(f"{self.c.CYAN}0.{self.c.ENDC} Exit")
            
            try:
                choice = int(input(f"\n{self.c.BOLD}Enter your choice: {self.c.ENDC}"))
                
                if choice == 0:
                    break
                elif choice == 1:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.display_word_info(word)
                elif choice == 2:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.edit_definition(word)
                elif choice == 3:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.add_definition(word)
                elif choice == 4:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.add_example(word)
                elif choice == 5:
                    limit = input(f"{self.c.BOLD}Enter limit (default: 10): {self.c.ENDC}").strip()
                    try:
                        limit = int(limit) if limit else 10
                    except ValueError:
                        limit = 10
                    self.list_problematic_words(limit)
                elif choice == 6:
                    limit = input(f"{self.c.BOLD}Enter limit (default: 10): {self.c.ENDC}").strip()
                    try:
                        limit = int(limit) if limit else 10
                    except ValueError:
                        limit = 10
                    self.find_missing_data(limit)
                elif choice == 7:
                    stats = linguistic_db.get_processing_stats(self.session)
                    print(f"\n{self.c.HEADER}{self.c.BOLD}Database Statistics:{self.c.ENDC}")
                    print(f"  Total words: {stats['total_words']}")
                    percent_with_defs = stats['words_with_definitions']/stats['total_words']*100 if stats['total_words'] > 0 else 0
                    print(f"  Words with definitions: {stats['words_with_definitions']} ({percent_with_defs:.1f}%)")
                    percent_with_examples = stats['words_with_examples']/stats['total_words']*100 if stats['total_words'] > 0 else 0
                    print(f"  Words with examples: {stats['words_with_examples']} ({percent_with_examples:.1f}%)")
                    print(f"  Total definitions: {stats['total_definitions']}")
                    print(f"  Total examples: {stats['total_examples']}")
                    print(f"  Overall completion: {stats['percent_complete']:.1f}%")
                elif choice == 8:
                    pos_type = input(f"{self.c.BOLD}Enter part of speech (noun, verb, adjective, etc.): {self.c.ENDC}").strip().lower()
                    if not pos_type:
                        print(f"{self.c.RED}Part of speech cannot be empty.{self.c.ENDC}")
                        continue
                    
                    limit = input(f"{self.c.BOLD}Enter limit (default: 20): {self.c.ENDC}").strip()
                    try:
                        limit = int(limit) if limit else 20
                    except ValueError:
                        limit = 20
                    
                    self.list_common_words_by_pos(pos_type, limit)
                elif choice == 9:
                    confirm = input(f"{self.c.BOLD}{self.c.RED}WARNING: This will migrate data from the old schema to the new one. Continue? (y/n): {self.c.ENDC}").strip().lower()
                    if confirm in ('y', 'yes'):
                        stats = linguistic_db.migrate_from_old_schema(self.session)
                        if "error" in stats:
                            print(f"{self.c.RED}Migration failed: {stats['error']}{self.c.ENDC}")
                        else:
                            print(f"{self.c.GREEN}Migration completed:{self.c.ENDC}")
                            print(f"  Words processed: {stats['words_processed']}")
                            print(f"  Definitions created: {stats['definitions_created']}")
                            print(f"  Words with POS but no lemma: {stats['words_with_pos_but_no_lemma']}")
                            print(f"  Words with lemma but no POS: {stats['words_with_lemma_but_no_pos']}")
                    else:
                        print(f"{self.c.YELLOW}Migration cancelled.{self.c.ENDC}")
            except Exception as e:
                logger.error(f"Error: {e}")