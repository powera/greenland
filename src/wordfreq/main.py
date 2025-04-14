#!/usr/bin/python3

"""Main script for linguistic analysis of word lists."""

import os
import logging
from typing import Dict, List, Optional, Any

import constants
from wordfreq import linguistic_db
from wordfreq.word_processor import WordProcessor
from wordfreq.linguistic_client import LinguisticClient
from wordfreq.export import LinguisticExporter
from wordfreq.reviewer import LinguisticReviewer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DB_PATH = constants.WORDFREQ_DB_PATH
DEFAULT_MODEL = constants.DEFAULT_MODEL

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Linguistic analysis of word lists")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Database file path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Initialize command
    init_parser = subparsers.add_parser("init", help="Initialize database")
    
    # Load command
    load_parser = subparsers.add_parser("load", help="Load words from a file")
    load_parser.add_argument("--word-column", type=int, default=0, help="Column index for words in CSV (0-based)")
    load_parser.add_argument("--rank-column", type=int, default=None, help="Column index for rank in CSV (0-based)")
    load_parser.add_argument("--no-header", action="store_true", help="CSV file has no header row")
    
    # Process command
    process_parser = subparsers.add_parser("process", help="Process words in database")
    process_parser.add_argument("--limit", type=int, default=None, help="Maximum number of words to process")
    process_parser.add_argument("--all", action="store_true", help="Process all words, including those already processed")
    process_parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing")
    process_parser.add_argument("--threads", type=int, default=4, help="Number of threads for parallel processing")
    process_parser.add_argument("--throttle", type=float, default=1.0, help="Time to wait between API calls (seconds)")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export linguistic data")
    export_parser.add_argument("--output", required=True, help="Output file path")
    export_parser.add_argument("--format", choices=["json", "csv", "simple", "nlp"], default="json", help="Output format")
    export_parser.add_argument("--min-confidence", type=float, default=0.0, help="Minimum confidence score (0-1)")
    export_parser.add_argument("--verified-only", action="store_true", help="Only include verified entries")
    
    # Review command
    review_parser = subparsers.add_parser("review", help="Interactive review and editing")
    review_parser.add_argument("--word", help="Word to display/edit (skips menu)")
    
    # Word command (process a single word)
    word_parser = subparsers.add_parser("word", help="Process a single word")
    word_parser.add_argument("word", help="Word to process")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    if args.command == "init":
        # Initialize database
        try:
            session = linguistic_db.create_database_session(args.db)
            session.close()
            print(f"Database initialized at: {args.db}")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            return 1
    
    elif args.command == "load":
        # Load words from file
        processor = WordProcessor(
            db_path=args.db,
            model=args.model,
            debug=args.debug
        )
        
        try:
            # Auto-detect format if not specified
            if not args.format:
                ext = os.path.splitext(args.file)[1].lower()
                if ext == '.json':
                    args.format = 'json'
                elif ext == '.csv':
                    args.format = 'csv'
                else:
                    args.format = 'text'
            
            # Load file
            if args.format == 'json':
                count = processor.load_words_from_json(args.file)
            elif args.format == 'csv':
                count = processor.load_words_from_csv(
                    args.file, 
                    word_column=args.word_column,
                    rank_column=args.rank_column,
                    has_header=not args.no_header
                )
            else:  # text
                count = processor.load_words_from_text(args.file)
                
            print(f"Loaded {count} words from {args.file}")
        except Exception as e:
            logger.error(f"Error loading words: {e}")
            return 1
        finally:
            processor.close()
    
    elif args.command == "process":
        # Process words in database
        processor = WordProcessor(
            db_path=args.db,
            model=args.model,
            threads=args.threads,
            batch_size=args.batch_size,
            throttle=args.throttle,
            debug=args.debug
        )
        
        try:
            stats = processor.process_all_words(
                limit=args.limit,
                skip_processed=not args.all
            )
            
            print(f"Processing complete: {stats['successful']}/{stats['processed']} words successful")
        except Exception as e:
            logger.error(f"Error processing words: {e}")
            return 1
        finally:
            processor.close()
    
    elif args.command == "export":
        # Export linguistic data
        exporter = LinguisticExporter(db_path=args.db)
        
        try:
            if args.format == "json":
                count = exporter.export_to_json(
                    args.output, 
                    min_confidence=args.min_confidence, 
                    verified_only=args.verified_only
                )
            elif args.format == "csv":
                count = exporter.export_to_csv(
                    args.output, 
                    min_confidence=args.min_confidence, 
                    verified_only=args.verified_only
                )
            elif args.format == "simple":
                count = exporter.export_simple_dictionary(
                    args.output, 
                    min_confidence=args.min_confidence
                )
            elif args.format == "nlp":
                count = exporter.export_nlp_format(
                    args.output, 
                    min_confidence=args.min_confidence
                )
            else:
                print(f"Unsupported format: {args.format}")
                return 1
                
            print(f"Exported {count} items to {args.output}")
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            return 1
        finally:
            exporter.close()
    
    elif args.command == "review":
        # Interactive review and editing
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
        except Exception as e:
            logger.error(f"Error during review: {e}")
            return 1
        finally:
            reviewer.close()
    
    elif args.command == "word":
        # Process a single word
        processor = WordProcessor(
            db_path=args.db,
            model=args.model,
            debug=args.debug
        )
        
        try:
            success = processor.process_single_word(args.word)
            if success:
                print(f"Successfully processed '{args.word}'")
            else:
                print(f"Failed to process '{args.word}'")
                return 1
        except Exception as e:
            logger.error(f"Error processing word: {e}")
            return 1
        finally:
            processor.close()
    
    elif args.command == "stats":
        # Show database statistics
        session = linguistic_db.create_database_session(args.db)
        
        try:
            stats = linguistic_db.get_processing_stats(session)
            
            print("Database Statistics:")
            print(f"  Total words: {stats['total_words']}")
            print(f"  Words with POS: {stats['words_with_pos']} ({stats['words_with_pos']/stats['total_words']*100:.1f}% if stats['total_words'] else 0)%)")
            print(f"  Words with lemma: {stats['words_with_lemma']} ({stats['words_with_lemma']/stats['total_words']*100:.1f}% if stats['total_words'] else 0)%)")
            print(f"  Fully processed words: {stats['words_complete']} ({stats['percent_complete']:.1f}%)")
            
            # List problematic words
            print("\nProblematic words (sample):")
            problematic = linguistic_db.list_problematic_words(session, limit=5)
            for item in problematic:
                print(f"  {item['word']} (rank {item['rank']}):")
                for pos_type, multiple, different, special, notes in item['parts_of_speech']:
                    flags = []
                    if multiple:
                        flags.append("multiple meanings")
                    if different:
                        flags.append("different POS")
                    if special:
                        flags.append("special case")
                    
                    print(f"    POS: {pos_type} {' - ' + ', '.join(flags) if flags else ''}")
                    if notes:
                        print(f"      Notes: {notes}")
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return 1
        finally:
            session.close()
    
    else:
        parser.print_help()
    
    return 0

if __name__ == "__main__":
    exit(main())("file", help="File to load")
    load_parser.add_argument("--format", choices=["json", "csv", "text"], help="File format (default: auto-detect)")
    load_parser.add_argument
