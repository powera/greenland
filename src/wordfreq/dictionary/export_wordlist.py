#!/usr/bin/python3

"""
Wordfreq Dictionary Export Tool

This tool exports words from the wordfreq database to a flat file,
ordered by their combined frequency rank (merged wordfreq order).
"""

import argparse
import logging
import sys
from typing import Optional, TextIO

import constants
from wordfreq.storage import database as linguistic_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def export_wordlist_to_file(
    output_file: TextIO,
    db_path: str = constants.WORDFREQ_DB_PATH,
    limit: Optional[int] = None,
    include_rank: bool = False,
    include_frequency: bool = False
) -> int:
    """
    Export words from the database to a flat file in frequency order.
    
    Args:
        output_file: File object to write to
        db_path: Path to SQLite database
        limit: Maximum number of words to export (None for all)
        include_rank: Whether to include frequency rank in output
        include_frequency: Whether to include frequency data in output
        
    Returns:
        Number of words exported
    """
    session = linguistic_db.create_database_session(db_path)
    
    try:
        # Get words ordered by combined frequency rank
        if limit is None:
            # Get all words with frequency rank
            words = linguistic_db.get_word_tokens_by_combined_frequency_rank(session, limit=1000000)
        else:
            words = linguistic_db.get_word_tokens_by_combined_frequency_rank(session, limit=limit)
        
        logger.info(f"Retrieved {len(words)} words from database")
        
        # Write words to file
        count = 0
        for word in words:
            if include_rank and include_frequency:
                # Get frequency information from first corpus (if available)
                freq_info = ""
                if word.frequencies:
                    first_freq = word.frequencies[0]
                    freq_info = f"\t{first_freq.frequency:.6f}" if first_freq.frequency else "\t0.000000"
                output_file.write(f"{word.frequency_rank}\t{word.token}{freq_info}\n")
            elif include_rank:
                output_file.write(f"{word.frequency_rank}\t{word.token}\n")
            elif include_frequency:
                # Get frequency information from first corpus (if available)
                freq_info = "0.000000"
                if word.frequencies:
                    first_freq = word.frequencies[0]
                    freq_info = f"{first_freq.frequency:.6f}" if first_freq.frequency else "0.000000"
                output_file.write(f"{word.token}\t{freq_info}\n")
            else:
                output_file.write(f"{word.token}\n")
            count += 1
        
        logger.info(f"Exported {count} words to file")
        return count
        
    finally:
        session.close()


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Export words from wordfreq database to a flat file in frequency order",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export top 1000 words to stdout
  python -m src.run_script wordfreq.dictionary.export_wordlist --limit 1000
  
  # Export all words to a file
  python -m src.run_script wordfreq.dictionary.export_wordlist -o wordlist.txt
  
  # Export with frequency ranks
  python -m src.run_script wordfreq.dictionary.export_wordlist -o wordlist.txt --include-rank
  
  # Export with frequency values
  python -m src.run_script wordfreq.dictionary.export_wordlist -o wordlist.txt --include-frequency
  
  # Export with both rank and frequency
  python -m src.run_script wordfreq.dictionary.export_wordlist -o wordlist.txt --include-rank --include-frequency
        """
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file path (default: stdout)"
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Maximum number of words to export (default: all words)"
    )
    
    parser.add_argument(
        "--include-rank", "-r",
        action="store_true",
        help="Include frequency rank as first column"
    )
    
    parser.add_argument(
        "--include-frequency", "-f",
        action="store_true",
        help="Include frequency value as additional column"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to database file (optional, uses default from constants)"
    )
    
    args = parser.parse_args()
    
    # Determine database path
    db_path = args.db_path if args.db_path else constants.WORDFREQ_DB_PATH
    
    # Open output file or use stdout
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                count = export_wordlist_to_file(
                    f, 
                    db_path=db_path,
                    limit=args.limit,
                    include_rank=args.include_rank,
                    include_frequency=args.include_frequency
                )
            print(f"Successfully exported {count} words to {args.output}")
        except IOError as e:
            logger.error(f"Error writing to file {args.output}: {e}")
            sys.exit(1)
    else:
        count = export_wordlist_to_file(
            sys.stdout,
            db_path=db_path,
            limit=args.limit,
            include_rank=args.include_rank,
            include_frequency=args.include_frequency
        )
        logger.info(f"Exported {count} words to stdout")


if __name__ == "__main__":
    main()