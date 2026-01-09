"""Pattern-based sentence generation for Buivolas."""

import itertools
import logging
import re
from typing import Dict, List, Optional, Tuple
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWord, SentencePatternWord

logger = logging.getLogger(__name__)


def strip_disambiguation(text: str) -> str:
    """
    Strip disambiguation info from lemma text.

    Removes parenthetical content from any position in the text.
    Examples:
        "mouse (computer)" -> "mouse"
        "they(f.) walk" -> "they walk"
        "(computer) monitor" -> "monitor"
    """
    result = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    result = re.sub(r"\s+", " ", result).strip()
    return result


class PatternSentenceGenerator:
    """Generator for pattern-based simple sentences."""

    def __init__(self, config: DataSourceConfig, dry_run: bool = False):
        self.config = config
        self.debug = config.debug
        self.dry_run = dry_run

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        return create_backend_session(self.config)

    def get_lemmas_for_slot(self, session, slot: Dict) -> List[Tuple[Lemma, str]]:
        query = session.query(Lemma).filter(
            Lemma.guid.isnot(None),
            Lemma.pos_type == slot["pos_type"],
        )

        if slot.get("pos_subtype") is not None:
            query = query.filter(Lemma.pos_subtype == slot["pos_subtype"])
        else:
            query = query.filter(Lemma.pos_subtype.is_(None))

        if slot.get("min_level"):
            query = query.filter(Lemma.difficulty_level >= slot["min_level"])
        if slot.get("max_level"):
            query = query.filter(Lemma.difficulty_level <= slot["max_level"])

        lemmas = query.all()
        return [(lemma, lemma.guid) for lemma in lemmas]

    def _slot_matches_lemma(self, slot: Dict, lemma: Lemma) -> bool:
        if slot["pos_type"] != lemma.pos_type:
            return False

        slot_subtype = slot.get("pos_subtype")
        if slot_subtype is None:
            return True

        return lemma.pos_subtype == slot_subtype

    def generate_combinations_for_lemma(
        self,
        session,
        pattern: Dict,
        target_lemma: Lemma,
        max_combinations: Optional[int] = None,
    ) -> List[Dict]:
        target_slot_name = None
        for slot in pattern["slots"]:
            if self._slot_matches_lemma(slot, target_lemma):
                target_slot_name = slot["name"]
                break

        if not target_slot_name:
            return []

        slot_lemmas = {}
        slot_names = []

        for slot in pattern["slots"]:
            slot_names.append(slot["name"])
            if slot["name"] == target_slot_name:
                slot_lemmas[slot["name"]] = [(target_lemma, target_lemma.guid)]
                continue

            lemmas = self.get_lemmas_for_slot(session, slot)
            if not lemmas:
                logger.warning(
                    "No lemmas found for slot %s (pos_type=%s, pos_subtype=%s)",
                    slot["name"],
                    slot["pos_type"],
                    slot.get("pos_subtype"),
                )
                return []

            slot_lemmas[slot["name"]] = lemmas

        combinations = []
        slot_lists = [slot_lemmas[name] for name in slot_names]
        total_combinations = 1
        for lst in slot_lists:
            total_combinations *= len(lst)

        logger.info(
            "Pattern %s: %s combinations with %s possible",
            pattern["pattern_id"],
            total_combinations,
            target_lemma.guid,
        )

        if max_combinations and total_combinations > max_combinations:
            logger.warning(
                "Limiting to %s combinations (from %s)",
                max_combinations,
                total_combinations,
            )

        for i, combo_tuple in enumerate(itertools.product(*slot_lists)):
            if max_combinations and i >= max_combinations:
                break

            combination = {
                "pattern_id": pattern["pattern_id"],
                "lemmas": {},
            }

            for slot_name, (lemma, guid) in zip(slot_names, combo_tuple):
                combination["lemmas"][slot_name] = (lemma, guid)

            combinations.append(combination)

        logger.info(
            "Generated %s combinations for pattern %s using %s",
            len(combinations),
            pattern["pattern_id"],
            target_lemma.guid,
        )
        return combinations

    def generate_all_combinations(
        self, session, pattern: Dict, max_combinations: Optional[int] = None
    ) -> List[Dict]:
        slot_lemmas = {}
        slot_names = []

        for slot in pattern["slots"]:
            lemmas = self.get_lemmas_for_slot(session, slot)
            if not lemmas:
                logger.warning(
                    "No lemmas found for slot %s (pos_type=%s, pos_subtype=%s)",
                    slot["name"],
                    slot["pos_type"],
                    slot.get("pos_subtype"),
                )
                return []
            slot_lemmas[slot["name"]] = lemmas
            slot_names.append(slot["name"])
            logger.info("Slot %s: %s lemmas", slot["name"], len(lemmas))

        slot_lists = [slot_lemmas[name] for name in slot_names]
        total_combinations = 1
        for lst in slot_lists:
            total_combinations *= len(lst)

        logger.info(
            "Pattern %s: %s total combinations possible",
            pattern["pattern_id"],
            total_combinations,
        )

        if max_combinations and total_combinations > max_combinations:
            logger.warning(
                "Limiting to %s combinations (from %s)",
                max_combinations,
                total_combinations,
            )

        combinations = []
        for i, combo_tuple in enumerate(itertools.product(*slot_lists)):
            if max_combinations and i >= max_combinations:
                break

            combination = {
                "pattern_id": pattern["pattern_id"],
                "lemmas": {},
            }

            for slot_name, (lemma, guid) in zip(slot_names, combo_tuple):
                combination["lemmas"][slot_name] = (lemma, guid)

            combinations.append(combination)

        logger.info(
            "Generated %s combinations for pattern %s",
            len(combinations),
            pattern["pattern_id"],
        )
        return combinations

    def build_template_text(self, pattern: Dict, filled_slots: Dict[str, Tuple[Lemma, str]]) -> str:
        en_sentence = pattern["en_template"]
        for slot_name, (lemma, guid) in filled_slots.items():
            lemma_text = strip_disambiguation(lemma.lemma_text)
            en_sentence = en_sentence.replace(f"[{slot_name}]", lemma_text)
        return en_sentence

    def lookup_fixed_words(self, session, pattern: Dict) -> List[Tuple[Lemma, str]]:
        fixed_lemmas = []
        for fixed_word in pattern.get("fixed_words", []):
            if fixed_word.get("guid"):
                query = session.query(Lemma).filter(
                    Lemma.guid == fixed_word["guid"],
                    Lemma.guid.isnot(None),
                )
                if fixed_word.get("pos_type"):
                    query = query.filter(Lemma.pos_type == fixed_word["pos_type"])
            else:
                query = session.query(Lemma).filter(
                    Lemma.lemma_text == fixed_word["lemma_text"],
                    Lemma.pos_type == fixed_word["pos_type"],
                    Lemma.guid.isnot(None),
                )
            lemma = query.first()
            if lemma:
                fixed_lemmas.append((lemma, lemma.guid))
            else:
                logger.warning(
                    "Could not find fixed word '%s' (pos_type=%s) for pattern %s",
                    fixed_word["lemma_text"],
                    fixed_word["pos_type"],
                    pattern["pattern_id"],
                )
        return fixed_lemmas

    def save_candidate_sentence(
        self, session, pattern: Dict, combination: Dict, template_text: str
    ):
        if self.dry_run:
            logger.debug("[DRY RUN] Would save candidate: %s", template_text)
            return None

        try:
            pattern_source = f"pattern:{pattern['pattern_id']}"
            existing_sentences = (
                session.query(Sentence).filter_by(source_filename=pattern_source).all()
            )

            combination_lemma_ids = {lemma.id for lemma, guid in combination["lemmas"].values()}

            for existing_sentence in existing_sentences:
                existing_lemma_ids = {
                    pw.lemma_id
                    for pw in session.query(SentencePatternWord)
                    .filter_by(sentence_id=existing_sentence.id)
                    .all()
                }

                if combination_lemma_ids == existing_lemma_ids:
                    status = "rejected" if existing_sentence.rejected else "duplicate"
                    logger.debug(
                        "Skipping %s sentence for pattern %s: %s (sentence %s)",
                        status,
                        pattern["pattern_id"],
                        template_text,
                        existing_sentence.id,
                    )
                    return "duplicate"

            sentence = Sentence(
                pattern_type=pattern.get("pattern_type"),
                source_filename=pattern_source,
                verified=False,
            )
            session.add(sentence)
            session.flush()

            translation = SentenceTranslation(
                sentence_id=sentence.id,
                language_code="en",
                translation_text=template_text,
                verified=False,
            )
            session.add(translation)

            # Store pattern definition in SentencePatternWord (permanent record)
            position = 0
            for slot_name, (lemma, guid) in combination["lemmas"].items():
                lemma_text = strip_disambiguation(lemma.lemma_text)

                pattern_word = SentencePatternWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    position=position,
                    slot_name=slot_name,
                    english_text=lemma_text,
                )
                session.add(pattern_word)
                position += 1

            # Add fixed words to pattern definition
            fixed_lemmas = self.lookup_fixed_words(session, pattern)
            for lemma, guid in fixed_lemmas:
                pattern_word = SentencePatternWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    position=position,
                    slot_name="fixed",
                    english_text=lemma.lemma_text,
                )
                session.add(pattern_word)
                position += 1

            session.commit()
            return sentence

        except Exception as e:
            logger.error("Failed to save candidate sentence: %s", e)
            session.rollback()
            return None

    def generate_candidates_for_pattern(
        self, pattern: Dict, max_combinations: Optional[int] = None
    ) -> Dict:
        logger.info("Generating candidates for pattern: %s", pattern["pattern_id"])

        session = self.get_session()
        try:
            combinations = self.generate_all_combinations(session, pattern, max_combinations)

            if not combinations:
                return {
                    "pattern_id": pattern["pattern_id"],
                    "success": False,
                    "error": "No valid lemma combinations found",
                }

            results = {
                "pattern_id": pattern["pattern_id"],
                "total": len(combinations),
                "success_count": 0,
                "duplicate_count": 0,
                "error_count": 0,
            }

            for i, combo in enumerate(combinations, 1):
                if i % 100 == 0:
                    logger.info("Processed %s/%s candidates...", i, len(combinations))

                template_text = self.build_template_text(pattern, combo["lemmas"])
                result = self.save_candidate_sentence(session, pattern, combo, template_text)

                if result == "duplicate":
                    results["duplicate_count"] += 1
                elif result or self.dry_run:
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1

            logger.info(
                "Pattern %s: saved %s/%s candidates, %s duplicates skipped",
                pattern["pattern_id"],
                results["success_count"],
                results["total"],
                results["duplicate_count"],
            )
            return results

        finally:
            session.close()

    def generate_candidates_for_guid(
        self, guid: str, max_combinations: Optional[int] = None
    ) -> Dict:
        session = self.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
            if not lemma:
                return {"success": False, "error": f"Lemma {guid} not found"}

            logger.info(
                "Generating pattern sentences for %s (%s)",
                lemma.lemma_text,
                lemma.guid,
            )

            eligible_patterns = []
            for pattern in SIMPLE_PATTERNS:
                if self.generate_combinations_for_lemma(
                    session, pattern, lemma, max_combinations=1
                ):
                    eligible_patterns.append(pattern)

            if not eligible_patterns:
                return {
                    "success": False,
                    "error": "No compatible patterns for lemma",
                    "processed": 0,
                    "stored": 0,
                    "duplicates": 0,
                    "errors": 0,
                }

            results = {
                "success": True,
                "processed": len(eligible_patterns),
                "stored": 0,
                "duplicates": 0,
                "errors": 0,
            }

            for pattern in eligible_patterns:
                combinations = self.generate_combinations_for_lemma(
                    session, pattern, lemma, max_combinations=max_combinations
                )

                for i, combo in enumerate(combinations, 1):
                    if i % 50 == 0:
                        logger.info(
                            "Pattern %s: processed %s/%s combinations",
                            pattern["pattern_id"],
                            i,
                            len(combinations),
                        )

                    template_text = self.build_template_text(pattern, combo["lemmas"])
                    result = self.save_candidate_sentence(session, pattern, combo, template_text)

                    if result == "duplicate":
                        results["duplicates"] += 1
                    elif result or self.dry_run:
                        results["stored"] += 1
                    else:
                        results["errors"] += 1

            if results["stored"] and not self.dry_run:
                session.commit()

            return results
        finally:
            session.close()

    def generate_candidates_all_patterns(self, max_per_pattern: Optional[int] = None) -> Dict:
        logger.info("Generating candidates for %s patterns", len(SIMPLE_PATTERNS))

        overall_results = {
            "patterns_processed": 0,
            "total_candidates": 0,
            "total_success": 0,
            "total_duplicates": 0,
            "total_errors": 0,
            "pattern_results": [],
        }

        for pattern in SIMPLE_PATTERNS:
            result = self.generate_candidates_for_pattern(pattern, max_combinations=max_per_pattern)
            overall_results["patterns_processed"] += 1
            overall_results["total_candidates"] += result.get("total", 0)
            overall_results["total_success"] += result.get("success_count", 0)
            overall_results["total_duplicates"] += result.get("duplicate_count", 0)
            overall_results["total_errors"] += result.get("error_count", 0)
            overall_results["pattern_results"].append(result)

        return overall_results
