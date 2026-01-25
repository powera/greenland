#!/usr/bin/env python3
"""
Erelis (Eagle) - False Lemma Match Detection

Detects sentences where a linked lemma's translation doesn't appear in
the sentence translation, indicating a potential semantic mismatch.

Example: "we had dinner" -> Chinese "我们吃了晚饭" (with 'eat')
If the English "have" lemma is linked but its Chinese translation (有)
doesn't appear in the sentence, this is flagged as a false match.

Usage:
    PYTHONPATH=src python src/agents/erelis.py --language zh
    PYTHONPATH=src python src/agents/erelis.py --language zh --limit 100
    PYTHONPATH=src python src/agents/erelis.py --language zh --guid V03_007
"""

import sys
from pathlib import Path

# Add src to path if needed
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.erelis.cli import main

if __name__ == "__main__":
    sys.exit(main())
