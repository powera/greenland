#!/usr/bin/python3

"""Interactive tool for reviewing and updating linguistic data."""

import logging
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

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
    
    def __init__(self, db_path: str = 'linguistics.sqlite'):
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
        
        # Parts of speech
        pos_entries = word.parts_of_speech
        print(f"\n{self.c.HEADER}Parts of Speech:{self.c.ENDC}")
        if not pos_entries:
            print(f"  {self.c.YELLOW}No parts of speech recorded{self.c.ENDC}")
        else:
            for i, pos in enumerate(pos_entries):
                flags = []
                if pos.multiple_meanings:
                    flags.append("multiple meanings")
                if pos.different_pos:
                    flags.append("different POS")
                if pos.special_case:
                    flags.append("special case")
                
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                verified_str = f" {self.c.GREEN}[✓]{self.c.ENDC}" if pos.verified else ""
                
                print(f"  {self.c.CYAN}[{i+1}]{self.c.ENDC} {pos.pos_type}{flag_str}{verified_str} - Confidence: {pos.confidence:.2f}")
                if pos.notes:
                    print(f"      Notes: {pos.notes}")
        
        # Lemmas
        lemma_entries = word.lemmas
        print(f"\n{self.c.HEADER}Lemmas:{self.c.ENDC}")
        if not lemma_entries:
            print(f"  {self.c.YELLOW}No lemmas recorded{self.c.ENDC}")
        else:
            for i, lemma in enumerate(lemma_entries):
                pos_str = f" ({lemma.pos_type})" if lemma.pos_type else ""
                verified_str = f" {self.c.GREEN}[✓]{self.c.ENDC}" if lemma.verified else ""
                
                print(f"  {self.c.CYAN}[{i+1}]{self.c.ENDC} {lemma.lemma}{pos_str}{verified_str} - Confidence: {lemma.confidence:.2f}")
                if lemma.notes:
                    print(f"      Notes: {lemma.notes}")
        
        return True
    
    def edit_pos(self, word_text: str) -> bool:
        """
        Edit parts of speech for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the edit was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current POS entries
        self.display_word_info(word_text)
        
        # Choose POS to edit
        pos_entries = word.parts_of_speech
        if not pos_entries:
            print(f"{self.c.YELLOW}No parts of speech to edit. Add one first.{self.c.ENDC}")
            return False
        
        try:
            choice = int(input(f"\n{self.c.BOLD}Enter POS number to edit (1-{len(pos_entries)}) or 0 to cancel: {self.c.ENDC}"))
            if choice == 0:
                return False
            
            if choice < 1 or choice > len(pos_entries):
                print(f"{self.c.RED}Invalid choice.{self.c.ENDC}")
                return False
            
            pos = pos_entries[choice-1]
            
            # Get new values
            print(f"\n{self.c.BOLD}Editing POS #{choice}. Press Enter to keep current values.{self.c.ENDC}")
            
            new_pos_type = input(f"Part of speech [{pos.pos_type}]: ").strip()
            new_pos_type = new_pos_type if new_pos_type else None
            
            new_confidence = input(f"Confidence [{pos.confidence}]: ").strip()
            try:
                new_confidence = float(new_confidence) if new_confidence else None
            except ValueError:
                new_confidence = None
            
            new_multiple = input(f"Multiple meanings (y/n) [{pos.multiple_meanings}]: ").strip().lower()
            if new_multiple in ('y', 'yes'):
                new_multiple = True
            elif new_multiple in ('n', 'no'):
                new_multiple = False
            else:
                new_multiple = None
            
            new_different = input(f"Different POS (y/n) [{pos.different_pos}]: ").strip().lower()
            if new_different in ('y', 'yes'):
                new_different = True
            elif new_different in ('n', 'no'):
                new_different = False
            else:
                new_different = None
            
            new_special = input(f"Special case (y/n) [{pos.special_case}]: ").strip().lower()
            if new_special in ('y', 'yes'):
                new_special = True
            elif new_special in ('n', 'no'):
                new_special = False
            else:
                new_special = None
            
            new_verified = input(f"Verified (y/n) [{pos.verified}]: ").strip().lower()
            if new_verified in ('y', 'yes'):
                new_verified = True
            elif new_verified in ('n', 'no'):
                new_verified = False
            else:
                new_verified = None
            
            new_notes = input(f"Notes [{pos.notes or ''}]: ").strip()
            new_notes = new_notes if new_notes else None
            
            # Update POS
            linguistic_db.update_part_of_speech(
                self.session,
                pos.id,
                pos_type=new_pos_type,
                confidence=new_confidence,
                multiple_meanings=new_multiple,
                different_pos=new_different,
                special_case=new_special,
                verified=new_verified,
                notes=new_notes
            )
            
            print(f"{self.c.GREEN}POS updated successfully.{self.c.ENDC}")
            return True
            
        except ValueError:
            print(f"{self.c.RED}Invalid input.{self.c.ENDC}")
            return False
    
    def add_pos(self, word_text: str) -> bool:
        """
        Add a new part of speech for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the addition was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current POS entries
        self.display_word_info(word_text)
        
        # Get new POS values
        print(f"\n{self.c.BOLD}Adding new part of speech for '{word.word}'.{self.c.ENDC}")
        
        pos_type = input("Part of speech: ").strip()
        if not pos_type:
            print(f"{self.c.RED}Part of speech cannot be empty.{self.c.ENDC}")
            return False
        
        confidence_str = input("Confidence (0-1) [1.0]: ").strip()
        try:
            confidence = float(confidence_str) if confidence_str else 1.0
        except ValueError:
            print(f"{self.c.RED}Invalid confidence value.{self.c.ENDC}")
            return False
        
        multiple = input("Multiple meanings (y/n) [n]: ").strip().lower()
        multiple = multiple in ('y', 'yes')
        
        different = input("Different POS (y/n) [n]: ").strip().lower()
        different = different in ('y', 'yes')
        
        special = input("Special case (y/n) [n]: ").strip().lower()
        special = special in ('y', 'yes')
        
        verified = input("Verified (y/n) [y]: ").strip().lower()
        verified = verified != 'n' and verified != 'no'
        
        notes = input("Notes: ").strip()
        notes = notes if notes else None
        
        # Add POS
        pos = linguistic_db.add_part_of_speech(
            self.session,
            word,
            pos_type=pos_type,
            confidence=confidence,
            multiple_meanings=multiple,
            different_pos=different,
            special_case=special,
            notes=notes
        )
        
        # Update verified status (can't be done in add_part_of_speech)
        linguistic_db.update_part_of_speech(
            self.session,
            pos.id,
            verified=verified
        )
        
        print(f"{self.c.GREEN}POS added successfully.{self.c.ENDC}")
        return True
    
    def edit_lemma(self, word_text: str) -> bool:
        """
        Edit lemmas for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the edit was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current lemma entries
        self.display_word_info(word_text)
        
        # Choose lemma to edit
        lemma_entries = word.lemmas
        if not lemma_entries:
            print(f"{self.c.YELLOW}No lemmas to edit. Add one first.{self.c.ENDC}")
            return False
        
        try:
            choice = int(input(f"\n{self.c.BOLD}Enter lemma number to edit (1-{len(lemma_entries)}) or 0 to cancel: {self.c.ENDC}"))
            if choice == 0:
                return False
            
            if choice < 1 or choice > len(lemma_entries):
                print(f"{self.c.RED}Invalid choice.{self.c.ENDC}")
                return False
            
            lemma = lemma_entries[choice-1]
            
            # Get new values
            print(f"\n{self.c.BOLD}Editing lemma #{choice}. Press Enter to keep current values.{self.c.ENDC}")
            
            new_lemma = input(f"Lemma [{lemma.lemma}]: ").strip()
            new_lemma = new_lemma if new_lemma else None
            
            new_pos = input(f"Part of speech [{lemma.pos_type or ''}]: ").strip()
            new_pos = new_pos if new_pos else None
            
            new_confidence = input(f"Confidence [{lemma.confidence}]: ").strip()
            try:
                new_confidence = float(new_confidence) if new_confidence else None
            except ValueError:
                new_confidence = None
            
            new_verified = input(f"Verified (y/n) [{lemma.verified}]: ").strip().lower()
            if new_verified in ('y', 'yes'):
                new_verified = True
            elif new_verified in ('n', 'no'):
                new_verified = False
            else:
                new_verified = None
            
            new_notes = input(f"Notes [{lemma.notes or ''}]: ").strip()
            new_notes = new_notes if new_notes else None
            
            # Update lemma
            linguistic_db.update_lemma(
                self.session,
                lemma.id,
                lemma=new_lemma,
                pos_type=new_pos,
                confidence=new_confidence,
                verified=new_verified,
                notes=new_notes
            )
            
            print(f"{self.c.GREEN}Lemma updated successfully.{self.c.ENDC}")
            return True
            
        except ValueError:
            print(f"{self.c.RED}Invalid input.{self.c.ENDC}")
            return False
    
    def add_lemma(self, word_text: str) -> bool:
        """
        Add a new lemma for a word.
        
        Args:
            word_text: Word to edit
            
        Returns:
            Whether the addition was successful
        """
        word = linguistic_db.get_word_by_text(self.session, word_text)
        if not word:
            print(f"{self.c.RED}Word '{word_text}' not found in the database.{self.c.ENDC}")
            return False
        
        # Display current lemma entries
        self.display_word_info(word_text)
        
        # Get new lemma values
        print(f"\n{self.c.BOLD}Adding new lemma for '{word.word}'.{self.c.ENDC}")
        
        lemma = input("Lemma: ").strip()
        if not lemma:
            print(f"{self.c.RED}Lemma cannot be empty.{self.c.ENDC}")
            return False
        
        pos_type = input("Part of speech: ").strip()
        pos_type = pos_type if pos_type else None
        
        confidence_str = input("Confidence (0-1) [1.0]: ").strip()
        try:
            confidence = float(confidence_str) if confidence_str else 1.0
        except ValueError:
            print(f"{self.c.RED}Invalid confidence value.{self.c.ENDC}")
            return False
        
        verified = input("Verified (y/n) [y]: ").strip().lower()
        verified = verified != 'n' and verified != 'no'
        
        notes = input("Notes: ").strip()
        notes = notes if notes else None
        
        # Add lemma
        lemma_obj = linguistic_db.add_lemma(
            self.session,
            word,
            lemma=lemma,
            pos_type=pos_type,
            confidence=confidence,
            notes=notes
        )
        
        # Update verified status (can't be done in add_lemma)
        linguistic_db.update_lemma(
            self.session,
            lemma_obj.id,
            verified=verified
        )
        
        print(f"{self.c.GREEN}Lemma added successfully.{self.c.ENDC}")
        return True

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
            flags = []
            for pos_data in item['parts_of_speech']:
                pos_type, multiple, different, special, notes = pos_data
                if multiple:
                    flags.append("multiple meanings")
                if different:
                    flags.append("different POS")
                if special:
                    flags.append("special case")
            
            flag_str = f" [{', '.join(set(flags))}]" if flags else ""
            
            print(f"{self.c.CYAN}{item['word']}{self.c.ENDC}{flag_str} (rank: {item['rank']})")
    
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
            missing = []
            if not word.parts_of_speech:
                missing.append("POS")
            if not word.lemmas:
                missing.append("lemma")
            
            print(f"{self.c.CYAN}{word.word}{self.c.ENDC} (rank: {word.frequency_rank}) - Missing: {', '.join(missing)}")
    
    def interactive_menu(self) -> None:
        """Run interactive menu for reviewing and editing words."""
        while True:
            print(f"\n{self.c.HEADER}{self.c.BOLD}Linguistic Data Reviewer{self.c.ENDC}")
            print(f"{self.c.CYAN}1.{self.c.ENDC} Display word information")
            print(f"{self.c.CYAN}2.{self.c.ENDC} Edit part of speech")
            print(f"{self.c.CYAN}3.{self.c.ENDC} Add part of speech")
            print(f"{self.c.CYAN}4.{self.c.ENDC} Edit lemma")
            print(f"{self.c.CYAN}5.{self.c.ENDC} Add lemma")
            print(f"{self.c.CYAN}6.{self.c.ENDC} List problematic words")
            print(f"{self.c.CYAN}7.{self.c.ENDC} Find words with missing data")
            print(f"{self.c.CYAN}8.{self.c.ENDC} Show statistics")
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
                        self.edit_pos(word)
                elif choice == 3:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.add_pos(word)
                elif choice == 4:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.edit_lemma(word)
                elif choice == 5:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.add_lemma(word)
                elif choice == 6:
                    limit = input(f"{self.c.BOLD}Enter limit (default: 10): {self.c.ENDC}").strip()
                    try:
                        limit = int(limit) if limit else 10
                    except ValueError:
                        limit = 10
                    self.list_problematic_words(limit)
                elif choice == 7:
                    limit = input(f"{self.c.BOLD}Enter limit (default: 10): {self.c.ENDC}").strip()
                    try:
                        limit = int(limit) if limit else 10
                    except ValueError:
                        limit = 10
                    self.find_missing_data(limit)
                elif choice == 8:
                    stats = linguistic_db.get_processing_stats(self.session)
                    print(f"\n{self.c.HEADER}{self.c.BOLD}Database Statistics:{self.c.ENDC}")
                    print(f"  Total words: {stats['total_words']}")
                    print(f"  Words with POS: {stats['words_with_pos']} ({stats['words_with_pos']/stats['total_words']*100:.1f}%)")
                    print(f"  Words with lemma: {stats['words_with_lemma']} ({stats['words_with_lemma']/stats['total_words']*100:.1f}%)")
                    print(f"  Fully processed: {stats['words_complete']} ({stats['percent_complete']:.1f}%)")
                else:
                    print(f"{self.c.RED}Invalid choice.{self.c.ENDC}")
            except ValueError:
                print(f"{self.c.RED}Invalid input.{self.c.ENDC}")
            except KeyboardInterrupt:
                print(f"\n{self.c.YELLOW}Operation cancelled.{self.c.ENDC}")
    
    def close(self):
        """Close database session."""
        if self.session:
            self.session.close()
            logger.info("Database session closed")

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Review and update linguistic data")
    parser.add_argument("--db", default="linguistics.sqlite", help="Database file path")
    parser.add_argument("--word", help="Word to display/edit (skips menu)")
    
    args = parser.parse_args()
    
    # Create reviewer
    reviewer = LinguisticReviewer(db_path=args.db)
    
    try:
        if args.word:
            # Display word and exit
            reviewer.display_word_info(args.word)
        else:
            # Run interactive menu
            reviewer.interactive_menu()
        
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        reviewer.close()

if __name__ == "__main__":
    main()
