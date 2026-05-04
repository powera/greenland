"""JSONL session implementation."""

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar

from sqlalchemy.orm import Query as SQLAlchemyQuery

from storage.backend.base import BaseSession
from storage.backend.jsonl import models

if TYPE_CHECKING:
    from storage.backend.jsonl.storage import JSONLStorage

T = TypeVar("T")


class JSONLSession(BaseSession):
    """JSONL session implementation.

    The session tracks pending changes and commits them to storage
    when commit() is called.

    For complex queries, this delegates to a temporary SQLite database.
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
        self._sqlite_session: Optional[Any] = None

    def _get_sqlite_session(self) -> Any:
        """Get or create a SQLite session for complex queries.

        Uses a cached SQLite engine from the storage instance so the in-memory
        database is populated once and reused across requests.

        Returns:
            A SQLAlchemy session connected to the cached in-memory SQLite database
        """
        if self._sqlite_session is None:
            engine = self._get_or_create_cached_engine()

            from sqlalchemy.orm import sessionmaker

            SessionFactory = sessionmaker(bind=engine)
            self._sqlite_session = SessionFactory()

        return self._sqlite_session

    def _get_or_create_cached_engine(self) -> Any:
        """Get or create a cached SQLite engine from the storage instance.

        The engine and its data are created once and shared across all sessions
        for the same storage instance. This avoids re-populating the in-memory
        SQLite DB on every request.

        Returns:
            A SQLAlchemy engine connected to the cached in-memory SQLite database
        """
        if self._storage._cached_sqlite_engine is not None:
            return self._storage._cached_sqlite_engine

        import logging

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from storage.models.schema import Base

        logger = logging.getLogger(__name__)
        logger.info("Creating cached in-memory SQLite database for JSONL backend queries")

        # Use StaticPool so all sessions share the same in-memory database
        engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)

        # Populate the database using a temporary session
        TempSessionFactory = sessionmaker(bind=engine)
        temp_session = TempSessionFactory()
        self._sqlite_session = temp_session
        self._populate_sqlite()

        # Log statistics about what was loaded
        from storage.models.grammar_fact import GrammarFact as SQLGrammarFact
        from storage.models.lemma_relation import (
            LemmaRelationGroup as SQLLemmaRelationGroup,
        )
        from storage.models.lemma_relation import (
            LemmaRelationMember as SQLLemmaRelationMember,
        )
        from storage.models.schema import Lemma as SQLLemma
        from storage.models.schema import LemmaTranslation
        from storage.models.schema import Sentence as SQLSentence
        from storage.models.schema import SentenceTranslation, SentenceWord

        assert temp_session is not None  # For type checking
        lemma_count = temp_session.query(SQLLemma).count()
        translation_count = temp_session.query(LemmaTranslation).count()
        grammar_fact_count = temp_session.query(SQLGrammarFact).count()
        relation_group_count = temp_session.query(SQLLemmaRelationGroup).count()
        relation_member_count = temp_session.query(SQLLemmaRelationMember).count()
        sentence_count = temp_session.query(SQLSentence).count()
        sentence_translation_count = temp_session.query(SentenceTranslation).count()
        sentence_word_count = temp_session.query(SentenceWord).count()

        logger.info(
            f"Populated cached SQLite DB: "
            f"{lemma_count} lemmas, "
            f"{translation_count} translations, "
            f"{grammar_fact_count} grammar_facts, "
            f"{relation_group_count} relation_groups, "
            f"{relation_member_count} relation_members, "
            f"{sentence_count} sentences, "
            f"{sentence_translation_count} sentence_translations, "
            f"{sentence_word_count} sentence_words"
        )

        # Cache the engine in storage for reuse by future sessions
        self._storage._cached_sqlite_engine = engine
        self._storage._sqlite_populated = True

        return engine

    def _get_model_map(self) -> Dict[Type[Any], Type[Any]]:
        """Get mapping from JSONL model classes to SQLAlchemy model classes.

        Returns:
            Dictionary mapping JSONL models to SQLAlchemy models
        """
        from storage.models.grammar_fact import GrammarFact as SQLGrammarFact
        from storage.models.lemma_relation import (
            LemmaRelationGroup as SQLLemmaRelationGroup,
        )
        from storage.models.lemma_relation import (
            LemmaRelationMember as SQLLemmaRelationMember,
        )
        from storage.models.schema import DerivativeForm as SQLDerivativeForm
        from storage.models.schema import Lemma as SQLLemma
        from storage.models.schema import (
            LemmaDifficultyOverride as SQLLemmaDifficultyOverride,
        )
        from storage.models.schema import LemmaTranslation as SQLLemmaTranslation
        from storage.models.schema import Sentence as SQLSentence
        from storage.models.schema import SentenceTranslation as SQLSentenceTranslation
        from storage.models.schema import SentenceWord as SQLSentenceWord

        return {
            models.Lemma: SQLLemma,
            models.LemmaTranslation: SQLLemmaTranslation,
            models.LemmaDifficultyOverride: SQLLemmaDifficultyOverride,
            models.DerivativeForm: SQLDerivativeForm,
            models.GrammarFact: SQLGrammarFact,
            models.LemmaRelationGroup: SQLLemmaRelationGroup,
            models.LemmaRelationMember: SQLLemmaRelationMember,
            models.Sentence: SQLSentence,
            models.SentenceTranslation: SQLSentenceTranslation,
            models.SentenceWord: SQLSentenceWord,
        }

    def _populate_sqlite(self) -> None:
        """Populate the temporary SQLite database with data from JSONL storage."""
        assert self._sqlite_session is not None  # For type checking
        from storage.models.grammar_fact import GrammarFact as SQLGrammarFact
        from storage.models.lemma_relation import (
            LemmaRelationGroup as SQLLemmaRelationGroup,
        )
        from storage.models.lemma_relation import (
            LemmaRelationMember as SQLLemmaRelationMember,
        )
        from storage.models.schema import DerivativeForm as SQLDerivativeForm
        from storage.models.schema import Lemma as SQLLemma
        from storage.models.schema import LemmaTranslation
        from storage.models.schema import Sentence as SQLSentence
        from storage.models.schema import SentenceTranslation, SentenceWord
        from storage.translation_helpers import compute_sort_key

        # Use bulk operations for better performance
        lemmas = []
        translations = []
        derivative_forms: list[dict] = []
        grammar_facts = []
        relation_groups = []
        relation_members = []
        sentences = []
        sentence_translations = []
        sentence_words = []

        # Prepare lemmas and translations
        for jsonl_lemma in self._storage.lemmas.values():
            # Only add fields that exist in both models
            lemma_dict = {
                "id": jsonl_lemma.id,
                "guid": jsonl_lemma.guid,
                "lemma_text": jsonl_lemma.lemma_text,
                "definition_text": jsonl_lemma.definition_text,
                "pos_type": jsonl_lemma.pos_type,
                "pos_subtype": jsonl_lemma.pos_subtype,
                "difficulty_level": jsonl_lemma.difficulty_level,
                "frequency_rank": jsonl_lemma.frequency_rank,
                "tags": jsonl_lemma.tags,
                "added_at": jsonl_lemma.added_at,
                "updated_at": jsonl_lemma.updated_at,
            }
            lemmas.append(lemma_dict)

            # Add translations
            for lang_code, translation in jsonl_lemma.translations.items():
                trans_entry: dict = {
                    "lemma_id": jsonl_lemma.id,
                    "language_code": lang_code,
                    "translation": translation,
                    "sort_key": compute_sort_key(lang_code, translation),
                }
                disambig = jsonl_lemma.translation_disambiguations.get(lang_code)
                if disambig:
                    trans_entry["disambiguation"] = disambig
                translations.append(trans_entry)

            # Add derivative forms (per-language inflections / base forms).
            # The combined-rank pass uses these to identify English lemmas, so
            # they must be present in the in-memory SQLite for golden mode.
            for lang_code, lang_forms in jsonl_lemma.derivative_forms.items():
                for form_name, form_data in lang_forms.items():
                    derivative_forms.append(
                        {
                            "lemma_id": jsonl_lemma.id,
                            "language_code": lang_code,
                            "grammatical_form": form_name,
                            "derivative_form_text": form_data.get("form", ""),
                            "is_base_form": form_data.get("is_base_form", False),
                            "ipa_pronunciation": form_data.get("ipa"),
                            "phonetic_pronunciation": form_data.get("phonetic"),
                        }
                    )

            # Add grammar facts
            for fact_data in jsonl_lemma.grammar_facts:
                grammar_facts.append(
                    {
                        "lemma_id": jsonl_lemma.id,
                        "language_code": fact_data.get("language_code", ""),
                        "fact_type": fact_data.get("fact_type", ""),
                        "fact_value": fact_data.get("fact_value"),
                        "notes": fact_data.get("notes"),
                        "verified": fact_data.get("verified", False),
                    }
                )

        # Prepare sentences and their translations/words
        for jsonl_sentence in self._storage.sentences.values():
            sentence_dict = {
                "id": jsonl_sentence.id,
                "guid": jsonl_sentence.guid,
                "pattern_type": jsonl_sentence.pattern_type,
                "tense": jsonl_sentence.tense,
                "minimum_level": jsonl_sentence.minimum_level,
                "source_filename": jsonl_sentence.source_filename,
                "verified": jsonl_sentence.verified,
                "added_at": jsonl_sentence.added_at,
                "updated_at": jsonl_sentence.updated_at,
            }
            sentences.append(sentence_dict)

            # Add translations
            for lang_code, translation_text in jsonl_sentence.translations.items():
                sentence_translations.append(
                    {
                        "sentence_id": jsonl_sentence.id,
                        "language_code": lang_code,
                        "translation_text": translation_text,
                    }
                )

            # Add words
            for word_data in jsonl_sentence.words:
                sentence_words.append(
                    {
                        "sentence_id": jsonl_sentence.id,
                        "lemma_id": word_data.get("lemma_id"),
                        "language_code": word_data.get("language_code", ""),
                        "position": word_data.get("position", 0),
                        "word_role": word_data.get("word_role"),
                        "grammatical_form": word_data.get("grammatical_form"),
                    }
                )

        # Prepare relation groups and members (resolve GUIDs to lemma IDs)
        guid_to_lemma_id = {lem.guid: lem.id for lem in self._storage.lemmas.values() if lem.guid}
        member_id_counter = 1
        for group in self._storage.relation_groups:
            relation_groups.append(
                {
                    "id": group.id,
                    "relation_type": group.relation_type,
                    "concept_label": group.concept_label,
                    "notes": group.notes,
                }
            )
            for member_guid in group.member_guids:
                lemma_id = guid_to_lemma_id.get(member_guid)
                if lemma_id is not None:
                    relation_members.append(
                        {
                            "id": member_id_counter,
                            "group_id": group.id,
                            "lemma_id": lemma_id,
                        }
                    )
                    member_id_counter += 1

        # Bulk insert
        if lemmas:
            self._sqlite_session.bulk_insert_mappings(SQLLemma, lemmas)
        if translations:
            self._sqlite_session.bulk_insert_mappings(LemmaTranslation, translations)
        if derivative_forms:
            self._sqlite_session.bulk_insert_mappings(SQLDerivativeForm, derivative_forms)
        if grammar_facts:
            self._sqlite_session.bulk_insert_mappings(SQLGrammarFact, grammar_facts)
        if relation_groups:
            self._sqlite_session.bulk_insert_mappings(SQLLemmaRelationGroup, relation_groups)
        if relation_members:
            self._sqlite_session.bulk_insert_mappings(SQLLemmaRelationMember, relation_members)
        if sentences:
            self._sqlite_session.bulk_insert_mappings(SQLSentence, sentences)
        if sentence_translations:
            self._sqlite_session.bulk_insert_mappings(SentenceTranslation, sentence_translations)
        if sentence_words:
            self._sqlite_session.bulk_insert_mappings(SentenceWord, sentence_words)

        self._sqlite_session.commit()

    def query(self, *entities: Any, **kwargs: Any) -> SQLAlchemyQuery:
        """Create a query for the given model class or columns.

        Loads JSONL data into ephemeral SQLite and returns a raw SQLAlchemy query.

        Args:
            *entities: The model class(es) to query, or column attributes
            **kwargs: Additional keyword arguments for the query

        Returns:
            A raw SQLAlchemy Query object (querying ephemeral SQLite)
        """
        self._check_not_closed()

        if len(entities) == 0:
            raise ValueError("query() requires at least one argument")

        # Map JSONL model classes to SQLAlchemy model classes
        model_map = self._get_model_map()

        # Convert entities to SQLAlchemy model classes
        mapped_entities = []
        for entity in entities:
            if entity in model_map:
                mapped_entities.append(model_map[entity])
            else:
                # For column attributes or already-mapped entities, pass through
                mapped_entities.append(entity)

        # Delegate all queries to SQLite
        sqlite_session = self._get_sqlite_session()
        result: SQLAlchemyQuery[Any] = sqlite_session.query(*mapped_entities, **kwargs)
        return result

    def _extract_lemma_translations(self) -> List[models.LemmaTranslation]:
        """Extract LemmaTranslation objects from nested Lemma data."""
        from storage.translation_helpers import compute_sort_key

        translations = []
        for lemma in self._storage.lemmas.values():
            for lang_code, translation_text in lemma.translations.items():
                pronunciation_data = lemma.translation_pronunciations.get(lang_code, {})
                trans = models.LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    translation=translation_text,
                    ipa_pronunciation=pronunciation_data.get("ipa_pronunciation"),
                    phonetic_pronunciation=pronunciation_data.get("phonetic_pronunciation"),
                    sort_key=compute_sort_key(lang_code, translation_text),
                    lemma=lemma,
                )
                translations.append(trans)
        return translations

    def _extract_difficulty_overrides(self) -> List[models.LemmaDifficultyOverride]:
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

    def _extract_derivative_forms(self) -> List[models.DerivativeForm]:
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

    def _extract_grammar_facts(self) -> List[models.GrammarFact]:
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

    def _extract_sentence_translations(self) -> List[models.SentenceTranslation]:
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

    def _extract_sentence_words(self) -> List[models.SentenceWord]:
        """Extract SentenceWord objects from nested Sentence data."""
        words = []
        for sentence in self._storage.sentences.values():
            for word_data in sentence.words:
                word = models.SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=word_data.get("lemma_id"),
                    language_code=word_data.get("language_code", ""),
                    position=word_data.get("position", 0),
                    word_role=word_data.get("word_role", ""),
                    grammatical_form=word_data.get("grammatical_form"),
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

        # Map JSONL model class to SQLAlchemy model class
        model_map = self._get_model_map()
        mapped_model_class = model_map.get(model_class, model_class)

        # Use SQLite for consistent querying
        sqlite_session = self._get_sqlite_session()
        result: Optional[T] = sqlite_session.get(mapped_model_class, id)
        return result

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
            if instance.ipa_pronunciation or instance.phonetic_pronunciation:
                lemma.translation_pronunciations[instance.language_code] = {
                    "ipa_pronunciation": instance.ipa_pronunciation,
                    "phonetic_pronunciation": instance.phonetic_pronunciation,
                }
            else:
                lemma.translation_pronunciations.pop(instance.language_code, None)
        elif isinstance(instance, models.LemmaDifficultyOverride):
            lemma.difficulty_overrides[instance.language_code] = instance.difficulty_level

        self._storage.save_lemma(lemma)

    def _update_derivative_form_in_lemma(self, instance: models.DerivativeForm) -> None:
        """Update a derivative form in a lemma.

        Args:
            instance: The derivative form
        """
        lemma = instance.lemma
        assert lemma is not None, "lemma must not be None"
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
        assert lemma is not None, "lemma must not be None"

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
        # Close SQLite session if it was created
        if self._sqlite_session is not None:
            self._sqlite_session.close()
            self._sqlite_session = None

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
