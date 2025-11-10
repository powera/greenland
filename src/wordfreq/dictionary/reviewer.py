#!/usr/bin/python3

"""Interactive tool for reviewing and updating linguistic data."""

import logging
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import constants
from wordfreq.storage import database as linguistic_db

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
        
        # Display frequency information from each corpus
        frequencies = word._word_token.frequencies
        if frequencies:
            print(f"\n{self.c.HEADER}Corpus Frequencies:{self.c.ENDC}")
            for freq in frequencies:
                corpus_name = freq.corpus.name
                rank_info = f"rank {freq.rank}" if freq.rank is not None else "no rank"
                freq_info = f", frequency {freq.frequency:.6f}" if freq.frequency is not None else ""
                print(f"  {self.c.CYAN}{corpus_name}:{self.c.ENDC} {rank_info}{freq_info}")
        else:
            print(f"\n{self.c.YELLOW}No corpus frequency data available{self.c.ENDC}")
        
        # Derivative forms (now the main data structure)
        derivative_forms = word.definitions  # This is actually derivative_forms due to the wrapper
        print(f"\n{self.c.HEADER}Derivative Forms:{self.c.ENDC}")
        if not derivative_forms:
            print(f"  {self.c.YELLOW}No derivative forms recorded{self.c.ENDC}")
        else:
            for i, derivative_form in enumerate(derivative_forms):
                verified_str = f" {self.c.GREEN}[✓]{self.c.ENDC}" if derivative_form.verified else ""
                
                # Definition text is in the lemma
                definition_text = derivative_form.lemma.definition_text
                print(f"  {self.c.CYAN}[{i+1}]{self.c.ENDC} {definition_text}{verified_str}")
                print(f"    {self.c.BLUE}Form:{self.c.ENDC} {derivative_form.derivative_form_text}")
                print(f"    {self.c.BLUE}Lemma:{self.c.ENDC} {derivative_form.lemma.lemma_text}")
                print(f"    {self.c.BLUE}Part of speech:{self.c.ENDC} {derivative_form.lemma.pos_type}")
                print(f"    {self.c.BLUE}Grammatical form:{self.c.ENDC} {derivative_form.grammatical_form}")
                if derivative_form.lemma.pos_subtype:
                    print(f"    {self.c.BLUE}Subtype:{self.c.ENDC} {derivative_form.lemma.pos_subtype}")
                if derivative_form.ipa_pronunciation:
                    print(f"    {self.c.BLUE}IPA:{self.c.ENDC} {derivative_form.ipa_pronunciation}")
                if derivative_form.phonetic_pronunciation:
                    print(f"    {self.c.BLUE}Phonetic Pronunciation:{self.c.ENDC} {derivative_form.phonetic_pronunciation}")
                
                # Translations are now in the lemma
                if derivative_form.lemma.chinese_translation:
                    print(f"    {self.c.BLUE}Chinese:{self.c.ENDC} {derivative_form.lemma.chinese_translation}")
                if derivative_form.lemma.french_translation:
                    print(f"    {self.c.BLUE}French:{self.c.ENDC} {derivative_form.lemma.french_translation}")
                if derivative_form.lemma.korean_translation:
                    print(f"    {self.c.BLUE}Korean:{self.c.ENDC} {derivative_form.lemma.korean_translation}")
                if derivative_form.lemma.swahili_translation:
                    print(f"    {self.c.BLUE}Swahili:{self.c.ENDC} {derivative_form.lemma.swahili_translation}")
                if derivative_form.lemma.lithuanian_translation:
                    print(f"    {self.c.BLUE}Lithuanian:{self.c.ENDC} {derivative_form.lemma.lithuanian_translation}")
                if derivative_form.lemma.vietnamese_translation:
                    print(f"    {self.c.BLUE}Vietnamese:{self.c.ENDC} {derivative_form.lemma.vietnamese_translation}")

                if derivative_form.notes:
                    print(f"    {self.c.BLUE}Notes:{self.c.ENDC} {derivative_form.notes}")

                # Add a separator between derivative forms
                if i < len(derivative_forms) - 1:
                    print()
        
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
            # Show unverified status
            unverified_count = sum(1 for definition in item['definitions'] if not definition.get('verified', True))
            flag_str = f" [unverified: {unverified_count}]" if unverified_count > 0 else ""
            
            print(f"{self.c.CYAN}{item['word']}{self.c.ENDC}{flag_str} (rank: {item['rank']})")
            # Show definition summaries
            for i, definition in enumerate(item['definitions']):
                verified_str = f" {self.c.GREEN}[✓]{self.c.ENDC}" if definition.get('verified', False) else f" {self.c.RED}[✗]{self.c.ENDC}"
                print(f"  {i+1}. {definition['pos']} - {definition['text'][:50]}...{verified_str}")
    
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
        word_width = max(len("Word"), max(len(item["token"]) for item in words))
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
            if not item['rank']:
                item['rank'] = "N/A"
            row = (
                f"{item['rank']:<6} "
                f"{item['token']:<{word_width}} "
                f"{item['lemma'] or '':<{lemma_width}} "
                f"{item['confidence']:<10.2f} "
                f"{definition}"
            )
            print(row)

    def list_common_words_by_pos_subtype(self, pos_type: str, pos_subtype: str, limit: int = 20) -> None:
        """
        List the most common words for a specified part of speech.
        
        Args:
            pos_type: Part of speech to filter by
            pos_subtype: Part of speech subtype to filter by
            limit: Maximum number of words to display
        """
        print(f"\n{self.c.HEADER}{self.c.BOLD}Most Common {pos_type.capitalize()}/{pos_subtype} Words:{self.c.ENDC}")
        
        words = linguistic_db.get_common_words_by_pos(self.session, pos_type, pos_subtype=pos_subtype, limit=limit)
        if not words:
            print(f"{self.c.YELLOW}No words found with part of speech '{pos_type}/{pos_subtype}'.{self.c.ENDC}")
            return
        
        # Calculate column widths
        word_width = max(len("Word"), max(len(item["token"]) for item in words))
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
            if not item['rank']:
                item['rank'] = "N/A"
            row = (
                f"{item['rank']:<6} "
                f"{item['token']:<{word_width}} "
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
        
        words = linguistic_db.get_word_tokens_needing_analysis(self.session, limit=limit)
        if not words:
            print(f"{self.c.GREEN}No words with missing data found.{self.c.ENDC}")
            return
        
        for word in words:
            print(f"{self.c.CYAN}{word.token}{self.c.ENDC} (rank: {word.frequency_rank}) - Missing: derivative forms")
    
    def show_word_list_access_info(self) -> None:
        """Show information about accessing word lists and the word categorizer tool."""
        print(f"\n{self.c.HEADER}{self.c.BOLD}Word List Access Information{self.c.ENDC}")
        print(f"\n{self.c.BLUE}Word Frequency Rankings:{self.c.ENDC}")
        print(f"  • Words are ranked using combined harmonic mean across multiple corpora")
        print(f"  • Lower rank numbers indicate higher frequency (rank 1 = most frequent)")
        print(f"  • Rankings combine data from Wikipedia, news, and other text sources")
        
        print(f"\n{self.c.BLUE}Accessing Word Lists Programmatically:{self.c.ENDC}")
        print(f"  {self.c.CYAN}from wordfreq.storage import database as linguistic_db{self.c.ENDC}")
        print(f"  {self.c.CYAN}session = linguistic_db.create_database_session(){self.c.ENDC}")
        print(f"  {self.c.CYAN}words = linguistic_db.get_word_tokens_by_combined_frequency_rank(session, limit=1000){self.c.ENDC}")
        print(f"  {self.c.CYAN}word_list = [token.token for token in words]{self.c.ENDC}")
        
        print(f"\n{self.c.BLUE}Word Categorizer Tool:{self.c.ENDC}")
        print(f"  A new tool is available for categorizing words using LLM analysis:")
        print(f"  {self.c.GREEN}python -m src.wordfreq.tools.word_categorizer \"category_name\"{self.c.ENDC}")
        
        print(f"\n{self.c.BLUE}Examples:{self.c.ENDC}")
        print(f"  {self.c.CYAN}# Categorize top 1000 words as animals{self.c.ENDC}")
        print(f"  {self.c.GREEN}python -m src.wordfreq.tools.word_categorizer \"animals\"{self.c.ENDC}")
        
        print(f"  {self.c.CYAN}# Find past participles in top 500 words{self.c.ENDC}")
        print(f"  {self.c.GREEN}python -m src.wordfreq.tools.word_categorizer \"past participles\" --limit 500{self.c.ENDC}")
        
        print(f"  {self.c.CYAN}# Find words similar to 'shiny' and save results{self.c.ENDC}")
        print(f"  {self.c.GREEN}python -m src.wordfreq.tools.word_categorizer \"words like shiny\" --save-json results.json{self.c.ENDC}")
        
        print(f"\n{self.c.BLUE}Tool Options:{self.c.ENDC}")
        print(f"  --limit N        Number of top words to analyze (default: 1000)")
        print(f"  --model NAME     LLM model to use (default: claude-3-5-sonnet-20241022)")
        print(f"  --no-explanations Hide explanations in output")
        print(f"  --save-json FILE Save results to JSON file")
        
        print(f"\n{self.c.BLUE}Output Format:{self.c.ENDC}")
        print(f"  The tool returns structured JSON with matching words, indicating whether")
        print(f"  each match represents the 'primary' meaning of the word (most common usage).")
        print(f"  Results are displayed in two sections: primary and secondary meanings.")
    
    def interactive_menu(self) -> None:
        """Run interactive menu for reviewing and editing words."""
        while True:
            print(f"\n{self.c.HEADER}{self.c.BOLD}Linguistic Data Reviewer{self.c.ENDC}")
            print(f"{self.c.CYAN}1.{self.c.ENDC} Display word information")
            print(f"{self.c.CYAN}5.{self.c.ENDC} List problematic words")
            print(f"{self.c.CYAN}6.{self.c.ENDC} Find words with missing data")
            print(f"{self.c.CYAN}7.{self.c.ENDC} Show statistics")
            print(f"{self.c.CYAN}8.{self.c.ENDC} List common words by part of speech")
            print(f"{self.c.CYAN}9.{self.c.ENDC} Show word list access information")

            print(f"{self.c.CYAN}0.{self.c.ENDC} Exit")

            try:
                choice = int(input(f"\n{self.c.BOLD}Enter your choice: {self.c.ENDC}"))

                if choice == 0:
                    break
                elif choice == 1:
                    word = input(f"{self.c.BOLD}Enter word: {self.c.ENDC}").strip()
                    if word:
                        self.display_word_info(word)
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
                    print(f"  Total word tokens: {stats['total_word_tokens']}")
                    percent_with_defs = stats['tokens_with_derivative_forms']/stats['total_word_tokens']*100 if stats['total_word_tokens'] > 0 else 0
                    print(f"  Tokens with derivative forms: {stats['tokens_with_derivative_forms']} ({percent_with_defs:.1f}%)")
                    print(f"  Total lemmas: {stats['total_lemmas']}")
                    print(f"  Total derivative forms: {stats['total_derivative_forms']}")
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
                    self.show_word_list_access_info()
            except Exception as e:
                logger.error(f"Error: {e}")

def main():
    """Main function to run the reviewer."""
    reviewer = LinguisticReviewer()
    reviewer.interactive_menu()

if __name__ == "__main__":
    main()