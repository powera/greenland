#!/usr/bin/env python3
"""
Povas - HTML Generation Agent for POS Subtypes

This agent generates HTML pages displaying all words for part-of-speech subtypes
in tabular form with comprehensive linguistic information.

"Povas" means "peacock" in Lithuanian - beautiful displays of information!

This script:
1. Queries the linguistic database for words organized by POS subtypes
2. Generates static HTML files for each POS subtype
3. Places these files in a subdirectory of OUTPUT_DIR
"""

import os
import logging
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func
import shutil

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm, ExampleSentence

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PovasAgent:
    """Agent for generating HTML pages for POS subtypes."""

    # Output directory
    POS_SUBTYPE_DIR = os.path.join(constants.OUTPUT_DIR, "pos_subtypes")

    # Style and script constants
    CSS_FILENAME = "pos_subtypes.css"
    CSS_TEMPLATE_PATH = os.path.join(constants.WORDFREQ_TEMPLATE_DIR, CSS_FILENAME)
    JS_FILENAME = "pos_subtypes.js"
    JS_TEMPLATE_PATH = os.path.join(constants.WORDFREQ_TEMPLATE_DIR, JS_FILENAME)

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Povas agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return get_session(self.db_path)

    def ensure_directory(self, directory: str) -> None:
        """Ensure the specified directory exists."""
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

    def get_words_by_pos_subtype(self, session, pos_type: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get words organized by POS subtype for a specific part of speech.
        Groups all derivative forms under their lemma.

        Args:
            session: Database session
            pos_type: Part of speech (noun, verb, adjective, adverb)

        Returns:
            Dictionary mapping subtypes to lists of word data
        """
        # Get the available subtypes for this POS
        subtypes = linguistic_db.get_subtype_values_for_pos(pos_type)

        # Query lemmas and their derivative forms, joining to word tokens
        query = session.query(
                Lemma,
                DerivativeForm,
                WordToken
            ).join(
                DerivativeForm, Lemma.id == DerivativeForm.lemma_id
            ).outerjoin(
                WordToken, DerivativeForm.word_token_id == WordToken.id
            ).filter(
                Lemma.pos_type == pos_type
            ).order_by(
                Lemma.lemma_text
            )

        # Organize by subtype, grouping all derivative forms under each lemma
        words_by_subtype = defaultdict(list)
        lemma_data = {}  # Track data by lemma to combine all derivative forms

        for lemma, derivative_form, word_token in query:
            subtype = lemma.pos_subtype or "uncategorized"
            if subtype not in subtypes:
                subtype = "uncategorized"

            # Create a unique key for this lemma
            lemma_key = (lemma.id, lemma.lemma_text, lemma.definition_text)

            if lemma_key not in lemma_data:
                # Get the first example if available
                example = ""
                if derivative_form.example_sentences and len(derivative_form.example_sentences) > 0:
                    example = derivative_form.example_sentences[0].example_text

                # Truncate definition and example if too long
                def_text = lemma.definition_text
                if len(def_text) > 150:
                    def_text = def_text[:147] + "..."

                if len(example) > 120:
                    example = example[:117] + "..."

                lemma_data[lemma_key] = {
                    "word": lemma.lemma_text,  # Display the lemma as the main word
                    "rank": word_token.frequency_rank if word_token else None,
                    "lemma": lemma.lemma_text,
                    "definition": def_text,
                    "example": example,
                    "pronunciation": derivative_form.phonetic_pronunciation or "",
                    "ipa": derivative_form.ipa_pronunciation or "",
                    "chinese": lemma.chinese_translation or "",
                    "french": lemma.french_translation or "",
                    "korean": lemma.korean_translation or "",
                    "swahili": lemma.swahili_translation or "",
                    "lithuanian": lemma.lithuanian_translation or "",
                    "vietnamese": lemma.vietnamese_translation or "",
                    "derivative_forms": [derivative_form.derivative_form_text] if derivative_form.derivative_form_text else [],
                    "grammatical_forms": [derivative_form.grammatical_form] if derivative_form.grammatical_form else [],
                    "subtype": subtype,
                    "min_rank": word_token.frequency_rank if word_token else None  # Track minimum rank for sorting
                }
            else:
                # Add this derivative form to the existing entry
                if derivative_form.derivative_form_text and derivative_form.derivative_form_text not in lemma_data[lemma_key]["derivative_forms"]:
                    lemma_data[lemma_key]["derivative_forms"].append(derivative_form.derivative_form_text)

                if derivative_form.grammatical_form and derivative_form.grammatical_form not in lemma_data[lemma_key]["grammatical_forms"]:
                    lemma_data[lemma_key]["grammatical_forms"].append(derivative_form.grammatical_form)

                # Update rank if this word token has a better (lower) rank
                if word_token and word_token.frequency_rank:
                    if lemma_data[lemma_key]["min_rank"] is None or word_token.frequency_rank < lemma_data[lemma_key]["min_rank"]:
                        lemma_data[lemma_key]["min_rank"] = word_token.frequency_rank
                        lemma_data[lemma_key]["rank"] = word_token.frequency_rank

        # Group by subtype
        for word_data in lemma_data.values():
            subtype = word_data.pop("subtype")  # Remove subtype from the data dict
            word_data.pop("min_rank")  # Remove the tracking field

            # Convert derivative forms list to a readable string
            word_data["forms"] = ", ".join(sorted(word_data["derivative_forms"]))
            del word_data["derivative_forms"]  # Remove the list, keep the string
            del word_data["grammatical_forms"]  # Remove grammatical forms (already in forms)

            words_by_subtype[subtype].append(word_data)

        return words_by_subtype

    def generate_index_page(self, session, env, pos_types: List[str]) -> None:
        """
        Generate the main index page with links to POS type pages.

        Args:
            session: Database session
            env: Jinja environment
            pos_types: List of POS types
        """
        pos_stats = {}

        for pos_type in pos_types:
            # Count unique lemmas for this POS (this matches the condensed view)
            lemma_count = session.query(func.count(Lemma.id.distinct()))\
                .filter(Lemma.pos_type == pos_type)\
                .scalar() or 0

            # Count derivative forms for this POS
            derivative_form_count = session.query(func.count(DerivativeForm.id))\
                .join(Lemma)\
                .filter(Lemma.pos_type == pos_type)\
                .scalar() or 0

            # Count subtypes used
            subtype_count = session.query(func.count(Lemma.pos_subtype.distinct()))\
                .filter(
                    Lemma.pos_type == pos_type,
                    Lemma.pos_subtype != None
                ).scalar() or 0

            # Get top 5 most common lemmas for this POS
            top_words = []
            query = session.query(Lemma.lemma_text)\
                .filter(Lemma.pos_type == pos_type)\
                .order_by(Lemma.lemma_text)\
                .limit(5)

            for row in query:
                top_words.append(row[0])

            pos_stats[pos_type] = {
                "word_count": lemma_count,
                "definition_count": derivative_form_count,
                "subtype_count": subtype_count,
                "top_words": top_words
            }

        # Load template
        template = env.get_template('pos_index.html')

        # Render template
        html = template.render(
            pos_stats=pos_stats,
            css_file=self.CSS_FILENAME
        )

        # Write to file
        with open(os.path.join(self.POS_SUBTYPE_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("Generated index page")

    def generate_pos_type_page(self, env, pos_type: str, words_by_subtype: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        Generate a page for a specific part of speech with links to subtypes.

        Args:
            env: Jinja environment
            pos_type: Part of speech
            words_by_subtype: Words organized by subtype
        """
        # Calculate stats for each subtype
        subtype_stats = {}
        total_words = 0

        for subtype, words in words_by_subtype.items():
            word_count = len(words)
            total_words += word_count

            # Get top 5 words by frequency rank
            top_words = sorted(words, key=lambda w: float("inf") if w.get("rank") is None else w.get("rank"))[:5]
            top_words = [word["word"] for word in top_words]

            subtype_stats[subtype] = {
                "word_count": word_count,
                "percentage": 0,  # Will calculate after loop
                "top_words": top_words
            }

        # Calculate percentages
        for subtype in subtype_stats:
            subtype_stats[subtype]["percentage"] = round(subtype_stats[subtype]["word_count"] / total_words * 100, 1)

        # Sort subtypes by word count
        sorted_subtypes = sorted(subtype_stats.items(), key=lambda x: x[1]["word_count"], reverse=True)

        # Load template
        template = env.get_template('pos_type.html')

        # Render template
        html = template.render(
            pos_type=pos_type,
            total_words=total_words,
            subtypes=subtype_stats,
            sorted_subtypes=sorted_subtypes,
            css_file=self.CSS_FILENAME
        )

        # Write to file
        with open(os.path.join(self.POS_SUBTYPE_DIR, f"{pos_type}.html"), "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Generated page for {pos_type}")

    def generate_subtype_page(self, env, pos_type: str, subtype: str, words: List[Dict[str, Any]]) -> None:
        """
        Generate a page for a specific POS subtype.

        Args:
            env: Jinja environment
            pos_type: Part of speech
            subtype: Subtype
            words: List of words for this subtype
        """
        # Load template
        template = env.get_template('pos_subtype.html')

        # Render template
        html = template.render(
            pos_type=pos_type,
            subtype=subtype,
            words=words,
            css_file=self.CSS_FILENAME,
            js_file=self.JS_FILENAME
        )

        # Write to file
        filename = f"{pos_type}_{subtype}.html"
        with open(os.path.join(self.POS_SUBTYPE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Generated page for {pos_type} subtype {subtype}")

    def copy_static_files(self) -> None:
        """Copy the CSS and JS files from templates to the output directory."""

        # Copy CSS file from templates to output directory
        shutil.copy2(self.CSS_TEMPLATE_PATH, os.path.join(self.POS_SUBTYPE_DIR, self.CSS_FILENAME))
        logger.info(f"Copied CSS file from templates to output directory: {self.CSS_FILENAME}")

        # Copy JS file from templates to output directory
        shutil.copy2(self.JS_TEMPLATE_PATH, os.path.join(self.POS_SUBTYPE_DIR, self.JS_FILENAME))
        logger.info(f"Copied JS file from templates to output directory: {self.JS_FILENAME}")

    def get_all_pos_types(self, session) -> List[str]:
        """
        Get all part of speech types from the database.

        Args:
            session: Database session

        Returns:
            List of all POS types found in the database
        """
        pos_types = session.query(Lemma.pos_type.distinct()).all()
        return [pos_type[0] for pos_type in pos_types]

    def generate_pos_subtype_pages(self) -> None:
        """
        Generate HTML pages for each POS subtype.
        """
        # Ensure output directory exists
        self.ensure_directory(self.POS_SUBTYPE_DIR)

        # Copy static files (CSS and JS)
        self.copy_static_files()

        session = self.get_session()
        try:
            # Parts of speech to process
            pos_types = self.get_all_pos_types(session)

            # Set up Jinja environment
            env = Environment(loader=FileSystemLoader(constants.WORDFREQ_TEMPLATE_DIR))

            # Generate index page
            self.generate_index_page(session, env, pos_types)

            # Generate individual POS type pages
            for pos_type in pos_types:
                logger.info(f"Processing {pos_type}...")

                # Get words by subtype
                words_by_subtype = self.get_words_by_pos_subtype(session, pos_type)

                if not words_by_subtype:
                    logger.warning(f"No words found for POS type: {pos_type}")
                    continue

                # Generate main POS type page
                self.generate_pos_type_page(env, pos_type, words_by_subtype)

                # Generate individual subtype pages
                for subtype, words in words_by_subtype.items():
                    self.generate_subtype_page(env, pos_type, subtype, words)

            logger.info(f"Generated all POS subtype pages in {self.POS_SUBTYPE_DIR}")
        finally:
            session.close()

    def generate_index_page_only(self) -> None:
        """
        Generate only the index page with links to all POS type pages.
        """
        # Ensure output directory exists
        self.ensure_directory(self.POS_SUBTYPE_DIR)

        # Copy static files (CSS and JS)
        self.copy_static_files()

        session = self.get_session()
        try:
            # Get all POS types from the database
            pos_types = self.get_all_pos_types(session)

            # Set up Jinja environment
            env = Environment(loader=FileSystemLoader(constants.WORDFREQ_TEMPLATE_DIR))

            # Generate index page
            self.generate_index_page(session, env, pos_types)

            logger.info(f"Generated index page in {self.POS_SUBTYPE_DIR}")
        finally:
            session.close()


def main():
    """Main entry point for the povas agent."""
    parser = argparse.ArgumentParser(
        description="Povas - HTML Generation Agent for POS Subtypes"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--index-only', action='store_true',
                        help='Generate only the index page')

    args = parser.parse_args()

    agent = PovasAgent(db_path=args.db_path, debug=args.debug)

    if args.index_only:
        # Generate only the index page
        agent.generate_index_page_only()
    else:
        # Generate all pages (index, POS types, and subtypes)
        agent.generate_pos_subtype_pages()

    logger.info(f"HTML generation complete. Files written to: {agent.POS_SUBTYPE_DIR}")


if __name__ == '__main__':
    main()
