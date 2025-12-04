"""JSONL session implementation."""

import datetime
from typing import Any, Optional, Type, TypeVar, Dict, List

from wordfreq.storage.backend.base import BaseSession, BaseQuery
from wordfreq.storage.backend.jsonl.query import JSONLQuery
from wordfreq.storage.backend.jsonl import models

T = TypeVar("T")


class JSONLSession(BaseSession):
    """JSONL session implementation.

    The session tracks pending changes and commits them to storage
    when commit() is called.
    """

    def __init__(self, storage: "JSONLStorage"):
        """Initialize JSONL session.

        Args:
            storage: The JSONLStorage instance
        """
        self._storage = storage
        self._pending_adds: list = []
        self._pending_deletes: list = []
        self._is_closed = False

    def query(self, model_class: Type[T]) -> BaseQuery[T]:
        """Create a query for the given model class.

        Args:
            model_class: The model class to query

        Returns:
            A JSONLQuery instance
        """
        self._check_not_closed()

        # Get the appropriate data source
        model_name = model_class.__name__

        if model_name == "Lemma":
            data = list(self._storage.lemmas.values())
        elif model_name == "Sentence":
            data = list(self._storage.sentences.values())
        elif model_name == "AudioQualityReview":
            data = list(self._storage.audio_reviews)
        elif model_name == "OperationLog":
            data = list(self._storage.operation_logs)
        elif model_name == "GuidTombstone":
            data = list(self._storage.tombstones)
        elif model_name == "LemmaTranslation":
            # Extract translations from lemmas
            data = self._extract_lemma_translations()
        elif model_name == "LemmaDifficultyOverride":
            data = self._extract_difficulty_overrides()
        elif model_name == "DerivativeForm":
            data = self._extract_derivative_forms()
        elif model_name == "GrammarFact":
            data = self._extract_grammar_facts()
        elif model_name == "SentenceTranslation":
            data = self._extract_sentence_translations()
        elif model_name == "SentenceWord":
            data = self._extract_sentence_words()
        else:
            data = []

        return JSONLQuery(data, model_class, self)

    def _extract_lemma_translations(self):
        """Extract LemmaTranslation objects from nested Lemma data."""
        translations = []
        for lemma in self._storage.lemmas.values():
            for lang_code, translation_text in lemma.translations.items():
                trans = models.LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    translation=translation_text,
                    lemma=lemma,
                )
                translations.append(trans)
        return translations

    def _extract_difficulty_overrides(self):
        """Extract LemmaDifficultyOverride objects from nested Lemma data."""
        overrides = []
        for lemma in self._storage.lemmas.values():
            for lang_code, level in lemma.difficulty_overrides.items():
                override = models.LemmaDifficultyOverride(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    difficulty_level=level,
                    lemma=lemma,
                )
                overrides.append(override)
        return overrides

    def _extract_derivative_forms(self):
        """Extract DerivativeForm objects from nested Lemma data."""
        forms = []
        for lemma in self._storage.lemmas.values():
            for lang_code, lang_forms in lemma.derivative_forms.items():
                for form_name, form_data in lang_forms.items():
                    form = models.DerivativeForm(
                        lemma_id=lemma.id,
                        language_code=lang_code,
                        grammatical_form=form_name,
                        derivative_form_text=form_data.get("form", ""),
                        is_base_form=form_data.get("is_base_form", False),
                        ipa_pronunciation=form_data.get("ipa"),
                        phonetic_pronunciation=form_data.get("phonetic"),
                        lemma=lemma,
                    )
                    forms.append(form)
        return forms

    def _extract_grammar_facts(self):
        """Extract GrammarFact objects from nested Lemma data."""
        facts = []
        for lemma in self._storage.lemmas.values():
            for fact_data in lemma.grammar_facts:
                fact = models.GrammarFact(
                    lemma_id=lemma.id,
                    language_code=fact_data.get("language_code", ""),
                    fact_type=fact_data.get("fact_type", ""),
                    fact_value=fact_data.get("fact_value"),
                    notes=fact_data.get("notes"),
                    verified=fact_data.get("verified", False),
                    lemma=lemma,
                )
                facts.append(fact)
        return facts

    def _extract_sentence_translations(self):
        """Extract SentenceTranslation objects from nested Sentence data."""
        translations = []
        for sentence in self._storage.sentences.values():
            for lang_code, text in sentence.translations.items():
                trans = models.SentenceTranslation(
                    sentence_id=sentence.id,
                    language_code=lang_code,
                    translation_text=text,
                    sentence=sentence,
                )
                translations.append(trans)
        return translations

    def _extract_sentence_words(self):
        """Extract SentenceWord objects from nested Sentence data."""
        words = []
        for sentence in self._storage.sentences.values():
            for word_data in sentence.words:
                word = models.SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=word_data.get("lemma_id"),
                    language_code=word_data.get("language_code", ""),
                    position=word_data.get("position", 0),
                    word_role=word_data.get("word_role"),
                    grammatical_form=word_data.get("grammatical_form"),
                    is_required_vocab=word_data.get("is_required_vocab", True),
                    sentence=sentence,
                )
                words.append(word)
        return words

    def get(self, model_class: Type[T], id: Any) -> Optional[T]:
        """Get a single instance by primary key.

        Args:
            model_class: The model class
            id: The primary key value (usually an integer ID)

        Returns:
            The instance or None if not found
        """
        self._check_not_closed()

        model_name = model_class.__name__

        if model_name == "Lemma":
            return self._storage.lemmas_by_id.get(id)
        elif model_name == "Sentence":
            return self._storage.sentences_by_id.get(id)
        elif model_name == "AudioQualityReview":
            for review in self._storage.audio_reviews:
                if review.id == id:
                    return review
        elif model_name == "OperationLog":
            for log in self._storage.operation_logs:
                if log.id == id:
                    return log
        elif model_name == "GuidTombstone":
            for tombstone in self._storage.tombstones:
                if tombstone.id == id:
                    return tombstone

        return None

    def add(self, instance: Any) -> None:
        """Add an instance to the session (mark for saving).

        Args:
            instance: The model instance to add
        """
        self._check_not_closed()
        self._pending_adds.append(instance)

    def delete(self, instance: Any) -> None:
        """Delete an instance from the session.

        Args:
            instance: The model instance to delete
        """
        self._check_not_closed()
        self._pending_deletes.append(instance)

    def commit(self) -> None:
        """Commit all pending changes to storage."""
        self._check_not_closed()

        # Process deletes first
        for instance in self._pending_deletes:
            if isinstance(instance, models.Lemma):
                self._storage.delete_lemma(instance)
            elif isinstance(instance, models.Sentence):
                self._storage.delete_sentence(instance)
            # Other types can be removed from lists

        # Process adds
        for instance in self._pending_adds:
            # Set timestamps
            if hasattr(instance, "added_at") and instance.added_at is None:
                instance.added_at = datetime.datetime.now()
            if hasattr(instance, "updated_at"):
                instance.updated_at = datetime.datetime.now()

            # Save to storage
            if isinstance(instance, models.Lemma):
                self._storage.save_lemma(instance)
            elif isinstance(instance, models.Sentence):
                self._storage.save_sentence(instance)
            elif isinstance(instance, models.AudioQualityReview):
                self._storage.append_audio_review(instance)
            elif isinstance(instance, models.OperationLog):
                self._storage.append_operation_log(instance)
            elif isinstance(instance, models.GuidTombstone):
                self._storage.append_tombstone(instance)
            elif isinstance(instance, (models.LemmaTranslation, models.LemmaDifficultyOverride)):
                # These are nested in Lemma, so update the parent lemma
                if instance.lemma:
                    self._update_nested_in_lemma(instance)
            elif isinstance(instance, models.DerivativeForm):
                if instance.lemma:
                    self._update_derivative_form_in_lemma(instance)
            elif isinstance(instance, models.GrammarFact):
                if instance.lemma:
                    self._update_grammar_fact_in_lemma(instance)
            elif isinstance(instance, (models.SentenceTranslation, models.SentenceWord)):
                # These are nested in Sentence
                if instance.sentence:
                    self._update_nested_in_sentence(instance)

        # Clear pending changes
        self._pending_adds.clear()
        self._pending_deletes.clear()

    def _update_nested_in_lemma(self, instance: Any) -> None:
        """Update nested objects in a lemma.

        Args:
            instance: The nested object (LemmaTranslation, etc.)
        """
        lemma = instance.lemma

        if isinstance(instance, models.LemmaTranslation):
            lemma.translations[instance.language_code] = instance.translation
        elif isinstance(instance, models.LemmaDifficultyOverride):
            lemma.difficulty_overrides[instance.language_code] = instance.difficulty_level

        self._storage.save_lemma(lemma)

    def _update_derivative_form_in_lemma(self, instance: models.DerivativeForm) -> None:
        """Update a derivative form in a lemma.

        Args:
            instance: The derivative form
        """
        lemma = instance.lemma
        lang_code = instance.language_code
        form_name = instance.grammatical_form

        if lang_code not in lemma.derivative_forms:
            lemma.derivative_forms[lang_code] = {}

        lemma.derivative_forms[lang_code][form_name] = {
            "form": instance.derivative_form_text,
            "is_base_form": instance.is_base_form,
            "ipa": instance.ipa_pronunciation,
            "phonetic": instance.phonetic_pronunciation,
        }

        self._storage.save_lemma(lemma)

    def _update_grammar_fact_in_lemma(self, instance: models.GrammarFact) -> None:
        """Update a grammar fact in a lemma.

        Args:
            instance: The grammar fact
        """
        lemma = instance.lemma

        # Check if fact already exists
        existing_fact = None
        for i, fact in enumerate(lemma.grammar_facts):
            if (
                fact.get("language_code") == instance.language_code
                and fact.get("fact_type") == instance.fact_type
            ):
                existing_fact = i
                break

        fact_data = {
            "language_code": instance.language_code,
            "fact_type": instance.fact_type,
            "fact_value": instance.fact_value,
            "notes": instance.notes,
            "verified": instance.verified,
        }

        if existing_fact is not None:
            lemma.grammar_facts[existing_fact] = fact_data
        else:
            lemma.grammar_facts.append(fact_data)

        self._storage.save_lemma(lemma)

    def _update_nested_in_sentence(self, instance: Any) -> None:
        """Update nested objects in a sentence.

        Args:
            instance: The nested object (SentenceTranslation, etc.)
        """
        sentence = instance.sentence

        if isinstance(instance, models.SentenceTranslation):
            sentence.translations[instance.language_code] = instance.translation_text
        elif isinstance(instance, models.SentenceWord):
            # Find existing word at position or append
            existing_word = None
            for i, word in enumerate(sentence.words):
                if (
                    word.get("language_code") == instance.language_code
                    and word.get("position") == instance.position
                ):
                    existing_word = i
                    break

            word_data = {
                "lemma_id": instance.lemma_id,
                "language_code": instance.language_code,
                "position": instance.position,
                "word_role": instance.word_role,
                "grammatical_form": instance.grammatical_form,
                "is_required_vocab": instance.is_required_vocab,
            }

            if existing_word is not None:
                sentence.words[existing_word] = word_data
            else:
                sentence.words.append(word_data)

        self._storage.save_sentence(sentence)

    def rollback(self) -> None:
        """Rollback all pending changes."""
        self._check_not_closed()
        self._pending_adds.clear()
        self._pending_deletes.clear()

    def flush(self) -> None:
        """Flush pending changes.

        For JSONL backend, this is the same as commit since we don't have transactions.
        """
        self.commit()

    def close(self) -> None:
        """Close the session."""
        self._is_closed = True

    def refresh(self, instance: Any) -> None:
        """Refresh an instance from storage.

        For JSONL backend, data is already in memory so this is a no-op.

        Args:
            instance: The model instance to refresh
        """
        self._check_not_closed()
        # No-op for JSONL since all data is in memory

    def expunge(self, instance: Any) -> None:
        """Remove an instance from the session without deleting it.

        Args:
            instance: The model instance to expunge
        """
        self._check_not_closed()
        if instance in self._pending_adds:
            self._pending_adds.remove(instance)
        if instance in self._pending_deletes:
            self._pending_deletes.remove(instance)

    def get_bind(self) -> Any:
        """Get the underlying storage.

        Returns:
            The JSONLStorage instance
        """
        return self._storage

    def _check_not_closed(self) -> None:
        """Check if session is closed and raise error if so."""
        if self._is_closed:
            raise RuntimeError("Session is closed")
