#!/usr/bin/python3

"""Tool for categorizing words from the frequency list using LLM analysis."""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import constants
from wordfreq.storage import database as linguistic_db
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty
from util.prompt_loader import get_context

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class WordMatch:
    """Represents a word that matches a category."""
    word: str
    is_primary_meaning: bool
    explanation: str

@dataclass
class CategorizationResult:
    """Results from word categorization analysis."""
    category: str
    matching_words: List[WordMatch]
    total_analyzed: int
    total_matches: int

class WordCategorizer:
    """Tool for categorizing words from frequency lists using LLM analysis."""
    
    def __init__(self, db_path: str = constants.WORDFREQ_DB_PATH, model: str = constants.DEFAULT_MODEL):
        """
        Initialize the word categorizer.
        
        Args:
            db_path: Path to the wordfreq database
            model: LLM model to use for categorization
        """
        self.db_path = db_path
        self.model = model
        self.session = linguistic_db.create_database_session(db_path)
        self.llm_client = UnifiedLLMClient()
        logger.info(f"Initialized WordCategorizer with model: {model}")
    
    def get_top_words(self, limit: int = 1000) -> List[str]:
        """
        Get the top N words from the frequency list using combined frequency ranks.
        
        Args:
            limit: Number of words to retrieve (default: 1000)
            
        Returns:
            List of word strings ordered by combined frequency rank
        """
        word_tokens = linguistic_db.get_word_tokens_by_combined_frequency_rank(
            self.session, limit=limit
        )
        return [token.token for token in word_tokens]
    
    def categorize_words(self, category: str, word_limit: int = 1000) -> CategorizationResult:
        """
        Categorize words from the frequency list using LLM analysis.
        
        Args:
            category: The category to match words against (e.g., "animals", "past participles", "words like shiny")
            word_limit: Number of top words to analyze (default: 1000)
            
        Returns:
            CategorizationResult with matching words and analysis
        """
        logger.info(f"Starting categorization for category: '{category}' with {word_limit} words")
        
        # Get the word list
        words = self.get_top_words(limit=word_limit)
        if not words:
            logger.warning("No words found with combined frequency ranks")
            return CategorizationResult(category, [], 0, 0)
        
        logger.info(f"Retrieved {len(words)} words by combined frequency rank")
        
        # Load the prompt template
        try:
            prompt_template = get_context("wordfreq", "word_categorizer")
        except FileNotFoundError as e:
            logger.error(f"Could not load prompt template: {e}")
            raise
        
        # Create the full prompt
        words_text = ", ".join(words)
        full_prompt = f"{prompt_template}\n\nCategory to match: {category}\n\nWords to analyze:\n{words_text}"
        
        # Define schema for word matches
        word_match_schema = Schema(
            "WordMatch",
            "A word that matches the category",
            {
                "word": SchemaProperty("string", "The matching word"),
                "is_primary_meaning": SchemaProperty("boolean", "Whether this represents the primary meaning of the word"),
                "explanation": SchemaProperty("string", "Brief explanation of why this word fits the category")
            }
        )
        
        # Define main response schema
        response_schema = Schema(
            "CategorizationResponse",
            "Response containing categorized words",
            {
                "category": SchemaProperty("string", "The category that was requested"),
                "matching_words": SchemaProperty("array", "List of words that match the category", array_items_schema=word_match_schema),
                "total_analyzed": SchemaProperty("integer", "Total number of words analyzed"),
                "total_matches": SchemaProperty("integer", "Total number of matching words found")
            }
        )
        
        # Make the LLM request
        logger.info(f"Sending categorization request to {self.model}")
        try:
            response = self.llm_client.generate_chat(
                prompt=full_prompt,
                model=self.model,
                json_schema=response_schema,
                timeout=300  # 5 minutes timeout for large word lists
            )
            
            if not response.structured_data:
                logger.error("LLM did not return structured data")
                raise RuntimeError("LLM response did not contain expected JSON structure")
            
            # Parse the response
            data = response.structured_data
            matching_words = [
                WordMatch(
                    word=match["word"],
                    is_primary_meaning=match["is_primary_meaning"],
                    explanation=match["explanation"]
                )
                for match in data["matching_words"]
            ]
            
            result = CategorizationResult(
                category=data["category"],
                matching_words=matching_words,
                total_analyzed=data["total_analyzed"],
                total_matches=data["total_matches"]
            )
            
            logger.info(f"Categorization complete: {result.total_matches} matches out of {result.total_analyzed} words")
            return result
            
        except Exception as e:
            logger.error(f"Error during LLM categorization: {e}")
            raise
    
    def print_results(self, result: CategorizationResult, show_explanations: bool = True) -> None:
        """
        Print categorization results in a formatted way.
        
        Args:
            result: The categorization result to display
            show_explanations: Whether to show explanations for each match
        """
        print(f"\n{'='*60}")
        print(f"WORD CATEGORIZATION RESULTS")
        print(f"{'='*60}")
        print(f"Category: {result.category}")
        print(f"Total words analyzed: {result.total_analyzed}")
        print(f"Total matches found: {result.total_matches}")
        print(f"Match rate: {result.total_matches/result.total_analyzed*100:.1f}%")
        
        if not result.matching_words:
            print("\nNo matching words found.")
            return
        
        # Separate primary and secondary meanings
        primary_matches = [w for w in result.matching_words if w.is_primary_meaning]
        secondary_matches = [w for w in result.matching_words if not w.is_primary_meaning]
        
        if primary_matches:
            print(f"\n{'='*40}")
            print(f"PRIMARY MEANING MATCHES ({len(primary_matches)})")
            print(f"{'='*40}")
            for match in primary_matches:
                if show_explanations:
                    print(f"• {match.word}: {match.explanation}")
                else:
                    print(f"• {match.word}")
        
        if secondary_matches:
            print(f"\n{'='*40}")
            print(f"SECONDARY MEANING MATCHES ({len(secondary_matches)})")
            print(f"{'='*40}")
            for match in secondary_matches:
                if show_explanations:
                    print(f"• {match.word}: {match.explanation}")
                else:
                    print(f"• {match.word}")
        
        # Summary lists
        print(f"\n{'='*40}")
        print(f"SUMMARY")
        print(f"{'='*40}")
        print(f"Primary meaning words: {', '.join([w.word for w in primary_matches])}")
        print(f"Secondary meaning words: {', '.join([w.word for w in secondary_matches])}")
    
    def save_results_json(self, result: CategorizationResult, filename: str) -> None:
        """
        Save categorization results to a JSON file.
        
        Args:
            result: The categorization result to save
            filename: Path to save the JSON file
        """
        data = {
            "category": result.category,
            "total_analyzed": result.total_analyzed,
            "total_matches": result.total_matches,
            "matching_words": [
                {
                    "word": match.word,
                    "is_primary_meaning": match.is_primary_meaning,
                    "explanation": match.explanation
                }
                for match in result.matching_words
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filename}")

def main():
    """Command-line interface for the word categorizer."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Categorize words from frequency lists using LLM analysis")
    parser.add_argument("category", help="Category to match words against (e.g., 'animals', 'past participles')")
    parser.add_argument("--limit", type=int, default=1000, help="Number of top words to analyze (default: 1000)")
    parser.add_argument("--model", default="claude-3-5-sonnet-20241022", help="LLM model to use")
    parser.add_argument("--no-explanations", action="store_true", help="Hide explanations in output")
    parser.add_argument("--save-json", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    try:
        categorizer = WordCategorizer(model=args.model)
        result = categorizer.categorize_words(
            category=args.category,
            word_limit=args.limit
        )
        
        categorizer.print_results(result, show_explanations=not args.no_explanations)
        
        if args.save_json:
            categorizer.save_results_json(result, args.save_json)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())