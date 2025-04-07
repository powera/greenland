#!/usr/bin/python3

"""Export linguistic data to various formats."""

import json
import csv
import logging
import os
from typing import Dict, List, Optional, Any, Set
from sqlalchemy import select, and_, func

import constants
from wordfreq import linguistic_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LinguisticExporter:
    """Export linguistic data to various formats."""
    
    def __init__(self, db_path: str = constants.WORDFREQ_DB_PATH):
        """
        Initialize exporter with database path.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.session = linguistic_db.create_database_session(db_path)
        logger.info(f"Connected to database: {db_path}")
    
    def export_to_json(self, output_path: str, min_confidence: float = 0.0, verified_only: bool = False) -> int:
        """
        Export linguistic data to a JSON file.
        
        Args:
            output_path: Output file path
            min_confidence: Minimum confidence score (0-1)
            verified_only: Whether to only include verified entries
            
        Returns:
            Number of words exported
        """
        logger.info(f"Exporting data to JSON: {output_path}")
        
        # Build query for words and join with POS and lemma data
        query = self.session.query(linguistic_db.Word)
        
        # Apply filters if requested
        if min_confidence > 0 or verified_only:
            if min_confidence > 0:
                query = query.join(linguistic_db.PartOfSpeech).filter(linguistic_db.PartOfSpeech.confidence >= min_confidence)
                query = query.join(linguistic_db.Lemma).filter(linguistic_db.Lemma.confidence >= min_confidence)
            if verified_only:
                query = query.join(linguistic_db.PartOfSpeech).filter(linguistic_db.PartOfSpeech.verified == True)
                query = query.join(linguistic_db.Lemma).filter(linguistic_db.Lemma.verified == True)
        
        # Order by rank
        query = query.order_by(linguistic_db.Word.frequency_rank)
        
        # Execute query and collect data
        words_data = {}
        for word_obj in query:
            word_data = {
                'word': word_obj.word,
                'rank': word_obj.frequency_rank,
                'parts_of_speech': [],
                'lemmas': []
            }
            
            # Add parts of speech
            for pos in word_obj.parts_of_speech:
                if (not min_confidence or pos.confidence >= min_confidence) and \
                   (not verified_only or pos.verified):
                    pos_data = {
                        'pos': pos.pos_type,
                        'confidence': pos.confidence,
                        'multiple_meanings': pos.multiple_meanings,
                        'different_pos': pos.different_pos,
                        'special_case': pos.special_case
                    }
                    if pos.notes:
                        pos_data['notes'] = pos.notes
                    word_data['parts_of_speech'].append(pos_data)
            
            # Add lemmas
            for lemma in word_obj.lemmas:
                if (not min_confidence or lemma.confidence >= min_confidence) and \
                   (not verified_only or lemma.verified):
                    lemma_data = {
                        'lemma': lemma.lemma,
                        'confidence': lemma.confidence
                    }
                    if lemma.pos_type:
                        lemma_data['pos'] = lemma.pos_type
                    if lemma.notes:
                        lemma_data['notes'] = lemma.notes
                    word_data['lemmas'].append(lemma_data)
            
            # Only include words that have both POS and lemma data
            if word_data['parts_of_speech'] and word_data['lemmas']:
                words_data[word_obj.word] = word_data
        
        # Write data to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'words': words_data,
                'metadata': {
                    'total_words': len(words_data),
                    'min_confidence': min_confidence,
                    'verified_only': verified_only
                }
            }, f, indent=2)
        
        logger.info(f"Exported {len(words_data)} words to {output_path}")
        return len(words_data)
    
    def export_to_csv(self, output_path: str, min_confidence: float = 0.0, verified_only: bool = False) -> int:
        """
        Export linguistic data to CSV files.
        
        Args:
            output_path: Base output file path (will append _words.csv, _pos.csv, etc.)
            min_confidence: Minimum confidence score (0-1)
            verified_only: Whether to only include verified entries
            
        Returns:
            Number of words exported
        """
        logger.info(f"Exporting data to CSV: {output_path}")
        
        # Prepare file paths
        base_dir = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        
        words_file = os.path.join(base_dir, f"{base_name}_words.csv")
        pos_file = os.path.join(base_dir, f"{base_name}_pos.csv")
        lemma_file = os.path.join(base_dir, f"{base_name}_lemmas.csv")
        
        # Query for words with ranking
        word_query = self.session.query(linguistic_db.Word)
        word_query = word_query.order_by(linguistic_db.Word.frequency_rank)
        words = list(word_query)
        
        # Write words CSV
        with open(words_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'word', 'rank'])
            
            for word in words:
                writer.writerow([word.id, word.word, word.frequency_rank])
        
        # Write parts of speech CSV
        pos_count = 0
        with open(pos_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['word_id', 'word', 'pos', 'confidence', 'multiple_meanings', 'different_pos', 'special_case', 'verified', 'notes'])
            
            for word in words:
                for pos in word.parts_of_speech:
                    if (not min_confidence or pos.confidence >= min_confidence) and \
                       (not verified_only or pos.verified):
                        writer.writerow([
                            word.id,
                            word.word,
                            pos.pos_type,
                            pos.confidence,
                            int(pos.multiple_meanings),
                            int(pos.different_pos),
                            int(pos.special_case),
                            int(pos.verified),
                            pos.notes or ''
                        ])
                        pos_count += 1
        
        # Write lemmas CSV
        lemma_count = 0
        with open(lemma_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['word_id', 'word', 'lemma', 'pos', 'confidence', 'verified', 'notes'])
            
            for word in words:
                for lemma in word.lemmas:
                    if (not min_confidence or lemma.confidence >= min_confidence) and \
                       (not verified_only or lemma.verified):
                        writer.writerow([
                            word.id,
                            word.word,
                            lemma.lemma,
                            lemma.pos_type or '',
                            lemma.confidence,
                            int(lemma.verified),
                            lemma.notes or ''
                        ])
                        lemma_count += 1
        
        logger.info(f"Exported {len(words)} words, {pos_count} POS entries, and {lemma_count} lemmas to CSV files")
        return len(words)
    
    def export_simple_dictionary(self, output_path: str, min_confidence: float = 0.5) -> int:
        """
        Export a simple dictionary mapping words to their primary POS and lemma.
        
        Format:
        {
            "word1": {"pos": "noun", "lemma": "word1"},
            "word2": {"pos": "verb", "lemma": "word"}
        }
        
        Args:
            output_path: Output file path
            min_confidence: Minimum confidence score (0-1)
            
        Returns:
            Number of words exported
        """
        logger.info(f"Exporting simple dictionary to: {output_path}")
        
        # Query all words
        words = self.session.query(linguistic_db.Word).order_by(linguistic_db.Word.frequency_rank).all()
        
        # Build dictionary
        dictionary = {}
        for word in words:
            # Get highest confidence POS
            best_pos = None
            best_pos_confidence = 0.0
            for pos in word.parts_of_speech:
                if pos.confidence >= min_confidence and pos.confidence > best_pos_confidence:
                    best_pos = pos.pos_type
                    best_pos_confidence = pos.confidence
            
            # Get highest confidence lemma
            best_lemma = None
            best_lemma_confidence = 0.0
            for lemma in word.lemmas:
                if lemma.confidence >= min_confidence and lemma.confidence > best_lemma_confidence:
                    best_lemma = lemma.lemma
                    best_lemma_confidence = lemma.confidence
            
            # Only add if we have both POS and lemma
            if best_pos and best_lemma:
                dictionary[word.word] = {
                    "pos": best_pos,
                    "lemma": best_lemma
                }
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(dictionary, f, indent=2)
        
        logger.info(f"Exported {len(dictionary)} words to simple dictionary: {output_path}")
        return len(dictionary)
    
    def export_nlp_format(self, output_path: str, min_confidence: float = 0.5) -> int:
        """
        Export data in a format suitable for NLP libraries.
        
        Format is a list of objects:
        [
            {"word": "running", "pos": "verb", "lemma": "run"},
            {"word": "better", "pos": "adjective", "lemma": "good"}
        ]
        
        Args:
            output_path: Output file path
            min_confidence: Minimum confidence score (0-1)
            
        Returns:
            Number of words exported
        """
        logger.info(f"Exporting NLP format to: {output_path}")
        
        # Query all words with POS and lemma
        query = self.session.query(
            linguistic_db.Word, 
            linguistic_db.PartOfSpeech,
            linguistic_db.Lemma
        ).join(
            linguistic_db.PartOfSpeech
        ).join(
            linguistic_db.Lemma
        ).filter(
            linguistic_db.PartOfSpeech.confidence >= min_confidence,
            linguistic_db.Lemma.confidence >= min_confidence
        ).order_by(
            linguistic_db.Word.frequency_rank
        )
        
        # Build list of entries
        entries = []
        for word, pos, lemma in query:
            entries.append({
                "word": word.word,
                "pos": pos.pos_type,
                "lemma": lemma.lemma
            })
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2)
        
        logger.info(f"Exported {len(entries)} entries to NLP format: {output_path}")
        return len(entries)
    
    def close(self):
        """Close database session."""
        if self.session:
            self.session.close()
            logger.info("Database session closed")

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Export linguistic data to various formats")
    parser.add_argument("--db", default="linguistics.sqlite", help="Database file path")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--format", choices=["json", "csv", "simple", "nlp"], default="json", 
                        help="Output format (default: json)")
    parser.add_argument("--min-confidence", type=float, default=0.0, 
                        help="Minimum confidence score (0-1)")
    parser.add_argument("--verified-only", action="store_true", 
                        help="Only include verified entries")
    
    args = parser.parse_args()
    
    # Create exporter
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
            return
            
        print(f"Exported {count} items to {args.output}")
        
    finally:
        exporter.close()

if __name__ == "__main__":
    main()
