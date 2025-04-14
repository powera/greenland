#!/usr/bin/python3

"""
Generate HTML pages that display all words for a part-of-speech subtype in tabular form.

This script:
1. Queries the linguistic database for words organized by POS subtypes
2. Generates static HTML files for each POS subtype
3. Places these files in a subdirectory of OUTPUT_DIR
"""

import os
import logging
import argparse
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func

import constants
from wordfreq import linguistic_db
from wordfreq.connection_pool import get_session

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Output directory
POS_SUBTYPE_DIR = os.path.join(constants.OUTPUT_DIR, "pos_subtypes")

# Style constants
CSS_FILENAME = "pos_subtypes.css"

def ensure_directory(directory: str) -> None:
    """Ensure the specified directory exists."""
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")


def get_words_by_pos_subtype(session, pos_type: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get words organized by POS subtype for a specific part of speech.
    
    Args:
        session: Database session
        pos_type: Part of speech (noun, verb, adjective, adverb)
        
    Returns:
        Dictionary mapping subtypes to lists of word data
    """
    # Get the available subtypes for this POS
    subtypes = linguistic_db.get_subtype_values_for_pos(pos_type)
    
    # Query words with definitions of the specified part of speech
    query = session.query(
            linguistic_db.Word, 
            linguistic_db.Definition
        ).join(
            linguistic_db.Definition
        ).filter(
            linguistic_db.Definition.pos_type == pos_type
        ).order_by(
            linguistic_db.Word.frequency_rank.nullslast(), 
            linguistic_db.Word.word
        )
    
    # Organize by subtype
    words_by_subtype = defaultdict(list)
    
    for word, definition in query:
        subtype = definition.pos_subtype or "uncategorized"
        if subtype not in subtypes:
            subtype = "uncategorized"
        
        # Use the first example if available
        example = ""
        if definition.examples and len(definition.examples) > 0:
            example = definition.examples[0].example_text
            
        # Truncate definition and example if too long
        def_text = definition.definition_text
        if len(def_text) > 100:
            def_text = def_text[:97] + "..."
            
        if len(example) > 120:
            example = example[:117] + "..."
        
        words_by_subtype[subtype].append({
            "word": word.word,
            "rank": word.frequency_rank,
            "lemma": definition.lemma,
            "definition": def_text,
            "example": example,
            "pronunciation": definition.phonetic_pronunciation or "",
            "ipa": definition.ipa_pronunciation or "",
            "chinese": definition.chinese_translation or ""
        })
    
    return words_by_subtype


def generate_pos_subtype_pages(session) -> None:
    """
    Generate HTML pages for each POS subtype.
    
    Args:
        session: Database session
    """
    # Ensure output directory exists
    ensure_directory(POS_SUBTYPE_DIR)
    
    # Create CSS file
    write_css_file()
    
    # Parts of speech to process
    pos_types = ["noun", "verb", "adjective", "adverb"]
    
    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))
    
    # Generate index page
    generate_index_page(session, env, pos_types)
    
    # Generate individual POS type pages
    for pos_type in pos_types:
        logger.info(f"Processing {pos_type}...")
        
        # Get words by subtype
        words_by_subtype = get_words_by_pos_subtype(session, pos_type)
        
        if not words_by_subtype:
            logger.warning(f"No words found for POS type: {pos_type}")
            continue
        
        # Generate main POS type page
        generate_pos_type_page(env, pos_type, words_by_subtype)
        
        # Generate individual subtype pages
        for subtype, words in words_by_subtype.items():
            generate_subtype_page(env, pos_type, subtype, words)
    
    logger.info(f"Generated all POS subtype pages in {POS_SUBTYPE_DIR}")


def generate_index_page(session, env, pos_types: List[str]) -> None:
    """
    Generate the main index page with links to POS type pages.
    
    Args:
        session: Database session
        env: Jinja environment
        pos_types: List of POS types
    """
    pos_stats = {}
    
    for pos_type in pos_types:
        # Count words and definitions for this POS
        word_count = session.query(func.count(linguistic_db.Word.id.distinct()))\
            .join(linguistic_db.Definition)\
            .filter(linguistic_db.Definition.pos_type == pos_type)\
            .scalar() or 0
            
        definition_count = session.query(func.count(linguistic_db.Definition.id))\
            .filter(linguistic_db.Definition.pos_type == pos_type)\
            .scalar() or 0
            
        # Count subtypes used
        subtype_count = session.query(func.count(linguistic_db.Definition.pos_subtype.distinct()))\
            .filter(
                linguistic_db.Definition.pos_type == pos_type,
                linguistic_db.Definition.pos_subtype != None
            ).scalar() or 0
        
        # Get top 5 most common words for this POS
        top_words = []
        query = session.query(linguistic_db.Word.word)\
            .join(linguistic_db.Definition)\
            .filter(linguistic_db.Definition.pos_type == pos_type)\
            .order_by(linguistic_db.Word.frequency_rank)\
            .limit(5)
            
        for row in query:
            top_words.append(row[0])
        
        pos_stats[pos_type] = {
            "word_count": word_count,
            "definition_count": definition_count,
            "subtype_count": subtype_count,
            "top_words": top_words
        }
    
    # Load template
    template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Glenora Linguistic Database - POS Subtypes</title>
    <link rel="stylesheet" href="{{ css_file }}">
</head>
<body>
    <div class="container">
        <header>
            <h1>Glenora Linguistic Database</h1>
            <p>Word classifications by part of speech and semantic subtype</p>
        </header>
        
        <section class="overview">
            <h2>Parts of Speech Overview</h2>
            <div class="pos-cards">
                {% for pos, stats in pos_stats.items() %}
                <div class="pos-card">
                    <h3><a href="{{ pos }}.html">{{ pos|title }}s</a></h3>
                    <p><strong>{{ stats.word_count }}</strong> unique words</p>
                    <p><strong>{{ stats.definition_count }}</strong> definitions</p>
                    <p><strong>{{ stats.subtype_count }}</strong> semantic subtypes</p>
                    <div class="top-words">
                        <p><strong>Top words:</strong> 
                        {% for word in stats.top_words %}
                            <span class="word">{{ word }}</span>{% if not loop.last %}, {% endif %}
                        {% endfor %}
                        </p>
                    </div>
                    <a href="{{ pos }}.html" class="view-button">View {{ pos|title }} Subtypes</a>
                </div>
                {% endfor %}
            </div>
        </section>
        
        <footer>
            <p>Generated by Glenora POS Subtype Generator</p>
        </footer>
    </div>
</body>
</html>"""

    # Create template from string
    template = env.from_string(template)
    
    # Render template
    html = template.render(
        pos_stats=pos_stats,
        css_file=CSS_FILENAME
    )
    
    # Write to file
    with open(os.path.join(POS_SUBTYPE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info("Generated index page")


def generate_pos_type_page(env, pos_type: str, words_by_subtype: Dict[str, List[Dict[str, Any]]]) -> None:
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
        top_words = sorted(words, key=lambda w: w.get("rank", float("inf")))[:5]
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
    template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ pos_type|title }}s - Glenora Linguistic Database</title>
    <link rel="stylesheet" href="{{ css_file }}">
</head>
<body>
    <div class="container">
        <header>
            <h1>{{ pos_type|title }}s</h1>
            <p>{{ total_words }} {{ pos_type }}s categorized into {{ subtypes|length }} semantic subtypes</p>
            <nav>
                <a href="index.html">Back to Overview</a>
            </nav>
        </header>
        
        <section class="subtype-overview">
            <h2>{{ pos_type|title }} Subtypes</h2>
            
            <div class="distribution-chart">
                {% for subtype, stats in sorted_subtypes %}
                <div class="chart-bar" style="width: {{ stats.percentage }}%;" title="{{ subtype }}: {{ stats.word_count }} words ({{ stats.percentage }}%)">
                    <div class="bar-label">{{ subtype }}</div>
                </div>
                {% endfor %}
            </div>
            
            <div class="subtype-cards">
                {% for subtype, stats in sorted_subtypes %}
                <div class="subtype-card">
                    <h3><a href="{{ pos_type }}_{{ subtype }}.html">{{ subtype|replace('_', ' ')|title }}</a></h3>
                    <p><strong>{{ stats.word_count }}</strong> words ({{ stats.percentage }}%)</p>
                    <div class="top-words">
                        <p><strong>Examples:</strong> 
                        {% for word in stats.top_words %}
                            <span class="word">{{ word }}</span>{% if not loop.last %}, {% endif %}
                        {% endfor %}
                        </p>
                    </div>
                    <a href="{{ pos_type }}_{{ subtype }}.html" class="view-button">View Words</a>
                </div>
                {% endfor %}
            </div>
        </section>
        
        <footer>
            <p>Generated by Glenora POS Subtype Generator</p>
        </footer>
    </div>
</body>
</html>"""

    # Create template from string
    template = env.from_string(template)
    
    # Render template
    html = template.render(
        pos_type=pos_type,
        total_words=total_words,
        subtypes=subtype_stats,
        sorted_subtypes=sorted_subtypes,
        css_file=CSS_FILENAME
    )
    
    # Write to file
    with open(os.path.join(POS_SUBTYPE_DIR, f"{pos_type}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"Generated page for {pos_type}")


def generate_subtype_page(env, pos_type: str, subtype: str, words: List[Dict[str, Any]]) -> None:
    """
    Generate a page for a specific POS subtype.
    
    Args:
        env: Jinja environment
        pos_type: Part of speech
        subtype: Subtype
        words: List of words for this subtype
    """
    # Load template
    template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ pos_type|title }} - {{ subtype|replace('_', ' ')|title }} - Glenora Linguistic Database</title>
    <link rel="stylesheet" href="{{ css_file }}">
</head>
<body>
    <div class="container">
        <header>
            <h1>{{ subtype|replace('_', ' ')|title }} {{ pos_type|title }}s</h1>
            <p>{{ words|length }} {{ pos_type }}s classified as "{{ subtype|replace('_', ' ') }}"</p>
            <nav>
                <a href="{{ pos_type }}.html">Back to {{ pos_type|title }} Subtypes</a> |
                <a href="index.html">Back to Overview</a>
            </nav>
        </header>
        
        <section class="word-table-section">
            <div class="table-controls">
                <input type="text" id="searchInput" placeholder="Search words...">
                <div class="field-toggles">
                    <label><input type="checkbox" data-column="pronunciation" checked> Pronunciation</label>
                    <label><input type="checkbox" data-column="ipa" checked> IPA</label>
                    <label><input type="checkbox" data-column="chinese" checked> Chinese</label>
                    <label><input type="checkbox" data-column="example" checked> Example</label>
                </div>
            </div>
            
            <table class="word-table">
                <thead>
                    <tr>
                        <th class="sortable" data-sort="word">Word</th>
                        <th class="sortable" data-sort="rank">Rank</th>
                        <th class="sortable" data-sort="lemma">Lemma</th>
                        <th>Definition</th>
                        <th class="pronunciation">Pronunciation</th>
                        <th class="ipa">IPA</th>
                        <th class="chinese">Chinese</th>
                        <th class="example">Example</th>
                    </tr>
                </thead>
                <tbody>
                    {% for word in words %}
                    <tr>
                        <td class="word">{{ word.word }}</td>
                        <td class="rank">{{ word.rank if word.rank else '-' }}</td>
                        <td class="lemma">{{ word.lemma }}</td>
                        <td class="definition">{{ word.definition }}</td>
                        <td class="pronunciation">{{ word.pronunciation }}</td>
                        <td class="ipa">{{ word.ipa }}</td>
                        <td class="chinese">{{ word.chinese }}</td>
                        <td class="example">{{ word.example }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </section>
        
        <footer>
            <p>Generated by Glenora POS Subtype Generator</p>
        </footer>
    </div>
    
    <script>
        // Simple table sorting and filtering
        document.addEventListener('DOMContentLoaded', function() {
            // Table sorting
            const table = document.querySelector('.word-table');
            const headers = table.querySelectorAll('th.sortable');
            const tableBody = table.querySelector('tbody');
            const rows = tableBody.querySelectorAll('tr');
            
            // Add click event to all sortable headers
            headers.forEach(header => {
                header.addEventListener('click', () => {
                    const column = header.dataset.sort;
                    const isNumeric = column === 'rank';
                    
                    // Check if we're sorting same column or different
                    const currentSort = header.getAttribute('data-current-sort');
                    const ascending = currentSort !== 'asc';
                    
                    // Reset all headers
                    headers.forEach(h => h.removeAttribute('data-current-sort'));
                    
                    // Set current sort
                    header.setAttribute('data-current-sort', ascending ? 'asc' : 'desc');
                    
                    // Convert rows to array for sorting
                    const rowsArray = Array.from(rows);
                    rowsArray.sort((rowA, rowB) => {
                        let valueA = rowA.querySelector(`td.${column}`).textContent.trim();
                        let valueB = rowB.querySelector(`td.${column}`).textContent.trim();
                        
                        if (isNumeric) {
                            // Handle numerical sorting (with '-' representing null)
                            valueA = valueA === '-' ? Infinity : parseInt(valueA);
                            valueB = valueB === '-' ? Infinity : parseInt(valueB);
                        }
                        
                        // String comparison for non-numeric
                        if (!isNumeric) {
                            if (valueA < valueB) return ascending ? -1 : 1;
                            if (valueA > valueB) return ascending ? 1 : -1;
                            return 0;
                        }
                        
                        // Numeric comparison
                        return ascending ? valueA - valueB : valueB - valueA;
                    });
                    
                    // Clear and re-add rows
                    tableBody.innerHTML = '';
                    rowsArray.forEach(row => tableBody.appendChild(row));
                });
            });
            
            // Table filtering
            const searchInput = document.getElementById('searchInput');
            searchInput.addEventListener('input', function() {
                const searchTerm = this.value.toLowerCase();
                
                rows.forEach(row => {
                    const word = row.querySelector('.word').textContent.toLowerCase();
                    const definition = row.querySelector('.definition').textContent.toLowerCase();
                    const example = row.querySelector('.example').textContent.toLowerCase();
                    
                    if (word.includes(searchTerm) || definition.includes(searchTerm) || example.includes(searchTerm)) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });
            });
            
            // Column visibility toggles
            const toggles = document.querySelectorAll('.field-toggles input');
            toggles.forEach(toggle => {
                toggle.addEventListener('change', function() {
                    const column = this.dataset.column;
                    const cells = document.querySelectorAll(`.${column}`);
                    
                    cells.forEach(cell => {
                        cell.style.display = this.checked ? '' : 'none';
                    });
                });
            });
        });
    </script>
</body>
</html>"""

    # Create template from string
    template = env.from_string(template)
    
    # Render template
    html = template.render(
        pos_type=pos_type,
        subtype=subtype,
        words=words,
        css_file=CSS_FILENAME
    )
    
    # Write to file
    filename = f"{pos_type}_{subtype}.html"
    with open(os.path.join(POS_SUBTYPE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"Generated page for {pos_type} subtype {subtype}")


def write_css_file() -> None:
    """Write the CSS file for styling the HTML pages."""
    css = """/* pos_subtypes.css */

/* Base styles */
:root {
    --primary-color: #3498db;
    --secondary-color: #2c3e50;
    --accent-color: #e74c3c;
    --light-color: #ecf0f1;
    --dark-color: #34495e;
    --success-color: #2ecc71;
    --warning-color: #f39c12;
    --font-main: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: var(--font-main);
    line-height: 1.6;
    color: #333;
    background-color: #f8f9fa;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

h1, h2, h3 {
    margin-bottom: 1rem;
    color: var(--secondary-color);
}

a {
    color: var(--primary-color);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Header styles */
header {
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #ddd;
}

header h1 {
    font-size: 2.5rem;
    color: var(--primary-color);
}

header p {
    font-size: 1.2rem;
    color: var(--dark-color);
}

header nav {
    margin-top: 1rem;
}

header nav a {
    margin-right: 1rem;
}

/* Section styles */
section {
    margin-bottom: 3rem;
}

section h2 {
    margin-bottom: 1.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--primary-color);
}

/* Card styles */
.pos-cards, .subtype-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
    margin-top: 20px;
}

.pos-card, .subtype-card {
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.pos-card:hover, .subtype-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.pos-card h3, .subtype-card h3 {
    color: var(--primary-color);
    margin-bottom: 15px;
}

.top-words {
    margin: 15px 0;
}

.word {
    font-weight: 500;
}

.view-button {
    display: inline-block;
    margin-top: 10px;
    padding: 8px 16px;
    background: var(--primary-color);
    color: white;
    border-radius: 4px;
    font-weight: 500;
    transition: background 0.3s ease;
}

.view-button:hover {
    background: var(--dark-color);
    text-decoration: none;
}

/* Distribution chart styles */
.distribution-chart {
    margin: 30px 0;
    background: var(--light-color);
    border-radius: 4px;
    overflow: hidden;
}

.chart-bar {
    height: 40px;
    background: var(--primary-color);
    margin-bottom: 2px;
    position: relative;
    min-width: 2%;  /* Ensure very small percentages are still visible */
}

.chart-bar:nth-child(odd) {
    background: #4dabdb;
}

.bar-label {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: white;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: calc(100% - 20px);
}

/* Table styles */
.word-table-section {
    overflow-x: auto;
}

.table-controls {
    display: flex;
    justify-content: space-between;
    margin-bottom: 15px;
    flex-wrap: wrap;
}

#searchInput {
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    width: 250px;
    margin-bottom: 10px;
}

.field-toggles label {
    margin-right: 15px;
    cursor: pointer;
}

.word-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 30px;
    background: white;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.word-table th, .word-table td {
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid #ddd;
}

.word-table th {
    background-color: var(--secondary-color);
    color: white;
    position: sticky;
    top: 0;
}

.word-table th.sortable {
    cursor: pointer;
}

.word-table th.sortable:hover {
    background-color: #3a546d;
}

.word-table th[data-current-sort="asc"]::after {
    content: " ↑";
}

.word-table th[data-current-sort="desc"]::after {
    content: " ↓";
}

.word-table tr:hover {
    background-color: rgba(52, 152, 219, 0.1);
}

.word-table td.word {
    font-weight: 600;
    color: var(--primary-color);
}

.word-table td.definition {
    max-width: 300px;
}

.word-table td.example {
    font-style: italic;
    color: #555;
    max-width: 300px;
}

/* Footer styles */
footer {
    border-top: 1px solid #ddd;
    padding-top: 20px;
    color: #777;
    text-align: center;
}

/* Responsive styles */
@media (max-width: 768px) {
    .pos-cards, .subtype-cards {
        grid-template-columns: 1fr;
    }
    
    .table-controls {
        flex-direction: column;
    }
    
    .field-toggles {
        margin-top: 10px;
    }
    
    .word-table td.definition,
    .word-table td.example {
        max-width: 200px;
    }
}"""
    
    # Write to file
    with open(os.path.join(POS_SUBTYPE_DIR, CSS_FILENAME), "w", encoding="utf-8") as f:
        f.write(css)
    
    logger.info(f"Created CSS file: {CSS_FILENAME}")


def create_templates_directory() -> None:
    """Create a templates directory for Jinja if it doesn't exist."""
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    ensure_directory(templates_dir)


def main():
    """Main function to run the generator."""
    parser = argparse.ArgumentParser(description="Generate HTML pages for POS subtypes")
    parser.add_argument("--db-path", type=str, default=constants.WORDFREQ_DB_PATH,
                        help="Path to linguistic database")
    args = parser.parse_args()
    
    # Create templates directory
    create_templates_directory()
    
    # Create output directory
    ensure_directory(POS_SUBTYPE_DIR)
    
    # Connect to database and generate pages
    session = get_session(args.db_path)
    try:
        generate_pos_subtype_pages(session)
    finally:
        session.close()
    
    logger.info(f"HTML generation complete. Files written to: {POS_SUBTYPE_DIR}")
    

if __name__ == "__main__":
    main()