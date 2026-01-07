"""Pattern-based sentence generation for Buivolas."""

import itertools
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.openai_batch_client import OpenAIBatchClient
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import (
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.translation.sentence import (
    build_translation_prompt,
    build_response_schema,
    store_translation_results,
)

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

        self.batch_client = OpenAIBatchClient(debug=self.debug)
        self.batch_session = create_batch_database_session()
        self.batch_manager = BatchQueueManager(
            self.batch_session, self.batch_client, debug=self.debug
        )

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

    def build_template_text(
        self, pattern: Dict, filled_slots: Dict[str, Tuple[Lemma, str]]
    ) -> str:
        en_sentence = pattern["en_template"]
        for slot_name, (lemma, guid) in filled_slots.items():
            lemma_text = strip_disambiguation(lemma.lemma_text)
            en_sentence = en_sentence.replace(f"[{slot_name}]", lemma_text)
        return en_sentence

    def lookup_fixed_words(self, session, pattern: Dict) -> List[Tuple[Lemma, str]]:
        fixed_lemmas = []
        for fixed_word in pattern.get("fixed_words", []):
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
                session.query(Sentence)
                .filter_by(source_filename=pattern_source)
                .all()
            )

            combination_lemma_ids = {
                lemma.id for lemma, guid in combination["lemmas"].values()
            }

            for existing_sentence in existing_sentences:
                existing_lemma_ids = {
                    sw.lemma_id
                    for sw in session.query(SentenceWord)
                    .filter_by(sentence_id=existing_sentence.id, language_code="en")
                    .all()
                    if sw.lemma_id is not None
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

            position = 0
            for slot_name, (lemma, guid) in combination["lemmas"].items():
                lemma_text = strip_disambiguation(lemma.lemma_text)

                sentence_word = SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    language_code="en",
                    position=position,
                    word_role=slot_name,
                    english_text=lemma_text,
                    target_language_text=lemma_text,
                )
                session.add(sentence_word)
                position += 1

            fixed_lemmas = self.lookup_fixed_words(session, pattern)
            for lemma, guid in fixed_lemmas:
                sentence_word = SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    language_code="en",
                    position=position,
                    word_role="fixed",
                    english_text=lemma.lemma_text,
                    target_language_text=lemma.lemma_text,
                )
                session.add(sentence_word)
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
            combinations = self.generate_all_combinations(
                session, pattern, max_combinations
            )

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
                result = self.save_candidate_sentence(
                    session, pattern, combo, template_text
                )

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

                    template_text = self.build_template_text(
                        pattern, combo["lemmas"]
                    )
                    result = self.save_candidate_sentence(
                        session, pattern, combo, template_text
                    )

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
            result = self.generate_candidates_for_pattern(
                pattern, max_combinations=max_per_pattern
            )
            overall_results["patterns_processed"] += 1
            overall_results["total_candidates"] += result.get("total", 0)
            overall_results["total_success"] += result.get("success_count", 0)
            overall_results["total_duplicates"] += result.get("duplicate_count", 0)
            overall_results["total_errors"] += result.get("error_count", 0)
            overall_results["pattern_results"].append(result)

        return overall_results

    def submit_batch_translation(
        self, target_languages: List[str], limit: Optional[int] = None, pattern_id: str = None
    ) -> Tuple[Optional[str], int]:
        session = self.get_session()
        try:
            from sqlalchemy import func as sql_func

            if pattern_id:
                query = (
                    session.query(Sentence)
                    .join(SentenceTranslation)
                    .filter(SentenceTranslation.language_code == "en")
                    .filter(Sentence.source_filename == f"pattern:{pattern_id}")
                )

                sentences_with_only_en = (
                    session.query(Sentence.id, sql_func.count(SentenceTranslation.id))
                    .join(SentenceTranslation)
                    .filter(Sentence.source_filename == f"pattern:{pattern_id}")
                    .group_by(Sentence.id)
                    .having(sql_func.count(SentenceTranslation.id) == 1)
                    .subquery()
                )

                query = query.filter(
                    Sentence.id.in_(session.query(sentences_with_only_en.c.id))
                )

                if limit:
                    query = query.limit(limit)

                sentences = query.all()
                logger.info(
                    "Found %s untranslated sentences for pattern %s",
                    len(sentences),
                    pattern_id,
                )

            else:
                pattern_source_query = (
                    session.query(Sentence.source_filename)
                    .join(SentenceTranslation)
                    .filter(SentenceTranslation.language_code == "en")
                    .filter(Sentence.source_filename.like("pattern:%"))
                    .distinct()
                )

                sentences_with_only_en = (
                    session.query(Sentence.id, sql_func.count(SentenceTranslation.id))
                    .join(SentenceTranslation)
                    .group_by(Sentence.id)
                    .having(sql_func.count(SentenceTranslation.id) == 1)
                    .subquery()
                )

                pattern_source_query = pattern_source_query.filter(
                    Sentence.id.in_(session.query(sentences_with_only_en.c.id))
                )

                pattern_sources = [row[0] for row in pattern_source_query.all()]

                if not pattern_sources:
                    logger.warning("No untranslated sentences found")
                    return None, 0

                logger.info(
                    "Found %s patterns with untranslated sentences",
                    len(pattern_sources),
                )

                sentences = []
                if limit:
                    per_pattern_limit = max(1, limit // len(pattern_sources))
                    logger.info(
                        "Distributing limit of %s across %s patterns (%s per pattern)",
                        limit,
                        len(pattern_sources),
                        per_pattern_limit,
                    )
                else:
                    per_pattern_limit = None

                for pattern_source in pattern_sources:
                    pattern_query = (
                        session.query(Sentence)
                        .filter(Sentence.source_filename == pattern_source)
                        .filter(
                            Sentence.id.in_(session.query(sentences_with_only_en.c.id))
                        )
                    )

                    if per_pattern_limit:
                        pattern_query = pattern_query.limit(per_pattern_limit)

                    pattern_sentences = pattern_query.all()
                    sentences.extend(pattern_sentences)

                    if limit and len(sentences) >= limit:
                        sentences = sentences[:limit]
                        break

                logger.info(
                    "Selected %s untranslated sentences across patterns",
                    len(sentences),
                )

            if not sentences:
                logger.warning("No untranslated sentences found")
                return None, 0

            requests_queued = 0
            for sentence in sentences:
                sentence_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id, language_code="en")
                    .all()
                )

                try:
                    context, prompt = build_translation_prompt(
                        sentence, sentence_words, target_languages, session
                    )
                except ValueError:
                    continue

                custom_id = f"sentence_{sentence.id}"
                full_prompt = f"{context}\n\n{prompt}"
                inner_schema = build_response_schema(target_languages)

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceTranslations",
                        "strict": True,
                        "schema": inner_schema,
                    },
                }

                request_body = {
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "response_format": response_format,
                }

                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name="buivolas",
                    operation_type="translate_sentence",
                    entity_id=sentence.id,
                    entity_type="sentence",
                )

                try:
                    self.batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions",
                    )
                    requests_queued += 1
                except ValueError as e:
                    logger.debug("Skipping sentence %s: %s", sentence.id, e)

            logger.info("Queued %s translation requests", requests_queued)

            if requests_queued > 0:
                pending_requests = self.batch_manager.get_pending_requests(
                    agent_name="buivolas", operation_type="translate_sentence"
                )
                batch_id, file_id = self.batch_manager.submit_batch(
                    pending_requests,
                    batch_metadata={
                        "agent": "buivolas",
                        "operation": "translate_sentences",
                    },
                )
                logger.info(
                    "Submitted batch %s with %s requests",
                    batch_id,
                    len(pending_requests),
                )
                return batch_id, len(pending_requests)

            return None, 0

        finally:
            session.close()

    def check_batch_status(self, batch_id: str) -> Dict:
        return self.batch_manager.check_batch_status(batch_id)

    def retrieve_batch_results(self, batch_id: str) -> int:
        count = self.batch_manager.retrieve_batch_results(batch_id)
        logger.info("Retrieved %s results from batch %s", count, batch_id)

        session = self.get_session()
        try:
            completed_requests = self.batch_manager.get_completed_requests(
                batch_id=batch_id
            )
            sentences_updated = 0

            for req in completed_requests:
                sentence_id = req.entity_id
                if not sentence_id:
                    continue

                try:
                    response = json.loads(req.response_body)
                    content = response["body"]["choices"][0]["message"]["content"]
                    translations = json.loads(content)

                    store_translation_results(sentence_id, translations, session)
                    sentences_updated += 1

                except Exception as e:
                    logger.error(
                        "Failed to apply results for sentence %s: %s",
                        sentence_id,
                        e,
                    )
                    session.rollback()

            logger.info("Updated %s sentences with translations", sentences_updated)
            return sentences_updated

        finally:
            session.close()
