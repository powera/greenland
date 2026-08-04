"""Scene-driven dialog generation: a scene brief plus a level, in, a dialog out.

This is the generation half of the Barsukas-first dialog flow. The caller (the
web UI, via a workqueue task) supplies a scene in plain words -- "buying
tomatoes at the grocery store" -- and a target difficulty level; this module
turns that into an LLM request and parses the reply into a :class:`SceneDraft`.
Storing the draft is the handler's job (``workqueue.handlers.conversations``),
and measuring which words in it we actually have is
``sentences.dialog_coverage``'s.

How this differs from the older keyword-driven path (``agents.sarka``), which
picks ~5 lemmas at a level and asks for a dialog around them:

* The scene leads. Vocabulary at the target level is offered as *encouraged*
  words, not a checklist, so the dialog says what the scene needs rather than
  bending around a word list.
* The level reaches the prompt. Previously the level only affected which words
  got sampled; the model was never told what level it was writing for.
* The cast comes back as data. Every proper name the dialog uses is returned in
  ``cast``, so names can be registered as :class:`~storage.models.name_entity.Name`
  rows instead of being rediscovered by string-matching the text later.

Nothing here writes to the database or reads configuration; it takes a session
only to sample encouraged vocabulary.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.models.name_entity import NAME_GENDERS, NAME_KINDS, normalize_name_text
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)

# Prompt category/type under prompts/ (prompts/conversations/scene/*.txt).
PROMPT_CATEGORY: str = "conversations"
PROMPT_TYPE: str = "scene"

# Default shape of a generated scene.
DEFAULT_NUM_TURNS: int = 10

# Language dialogs are generated in, used here only to pick sentence-splitting
# rules. Mirrors GENERATION_LANG in workqueue.handlers.conversations.scene,
# which owns the storage side of the same decision.
GENERATION_LANG: str = "en"

# How many level-appropriate words to offer as encouraged vocabulary. Large
# enough to steer register, small enough that the model does not treat it as a
# checklist to exhaust.
ENCOURAGED_VOCABULARY_SIZE: int = 40

# Share of the encouraged sample drawn from the target level itself; the rest
# comes from levels below it, so the dialog can still say ordinary things.
TARGET_LEVEL_SHARE: float = 0.5


@dataclass
class SceneRequest:
    """What the user asked for on the "new dialog" form."""

    scene: str
    target_level: int
    num_turns: int = DEFAULT_NUM_TURNS
    model: Optional[str] = None
    # Free-form extra direction ("make them strangers", "end without a sale").
    notes: Optional[str] = None

    def validate(self) -> None:
        """Raise ValueError when the request cannot be generated from.

        Raises:
            ValueError: If the scene is empty, the level is not positive, or
                the turn count is outside a sane range.
        """
        if not self.scene.strip():
            raise ValueError("A dialog needs a scene, e.g. 'buying tomatoes at the grocery store'")
        if self.target_level < 1:
            raise ValueError(f"Target level must be 1 or greater, got {self.target_level}")
        if not 2 <= self.num_turns <= 40:
            raise ValueError(f"Turn count must be between 2 and 40, got {self.num_turns}")


@dataclass
class SceneTurn:
    """One spoken turn: who says it, and the sentences they say.

    A turn holds a *list* of sentences rather than one string because each
    sentence becomes its own ``Sentence`` row. The generator returns the split
    directly -- it already knows where its own sentence boundaries are, which
    beats inferring them back out of flattened text -- and
    :func:`parse_scene_response` normalizes whatever comes back.
    """

    speaker: str
    sentences: List[str]

    @property
    def text(self) -> str:
        """The whole turn as one string, for callers that want the line."""
        return " ".join(self.sentences)


@dataclass
class CastMember:
    """A proper name the dialog uses, as reported by the generator."""

    name_text: str
    kind: str = "given_name"
    gender: Optional[str] = None
    role: Optional[str] = None

    def normalized(self) -> "CastMember":
        """Return a copy with the name normalized and the vocabularies enforced.

        Unknown kinds and genders are coerced rather than rejected: a usable
        dialog with a mislabeled name is worth more than a failed generation,
        and the label is reviewed in Barsukas anyway.
        """
        kind = self.kind if self.kind in NAME_KINDS else "other"
        gender = self.gender if self.gender in NAME_GENDERS else None
        return CastMember(
            name_text=normalize_name_text(self.name_text),
            kind=kind,
            gender=gender,
            role=self.role or None,
        )


@dataclass
class SceneDraft:
    """A generated dialog, before it becomes Conversation/Sentence rows."""

    title: str
    theme: Optional[str]
    turns: List[SceneTurn]
    cast: List[CastMember] = field(default_factory=list)
    scene: str = ""
    target_level: int = 1
    source_model: Optional[str] = None
    encouraged_words: List[str] = field(default_factory=list)

    @property
    def lines(self) -> List[str]:
        """The spoken text of every turn, in order."""
        return [turn.text for turn in self.turns]

    def cast_names(self) -> List[str]:
        """Every distinct name text in the cast, in order of first appearance."""
        seen: set[str] = set()
        out: List[str] = []
        for member in self.cast:
            if member.name_text and member.name_text not in seen:
                seen.add(member.name_text)
                out.append(member.name_text)
        return out


def sample_encouraged_vocabulary(
    session: Session,
    target_level: int,
    *,
    sample_size: int = ENCOURAGED_VOCABULARY_SIZE,
    rng: Optional[random.Random] = None,
) -> List[str]:
    """Sample curated words at or below the target level to steer register.

    Half the sample comes from the target level itself and the rest from the
    levels below it, so the model sees both the new vocabulary the level is
    about and the everyday words it needs to build sentences around them.

    Args:
        session: Database session.
        target_level: The level the dialog is being written for.
        sample_size: Total words to return.
        rng: Optional random source, for deterministic tests.

    Returns:
        Lemma texts, target-level words first. May be shorter than
        ``sample_size``, or empty when the database has no curated words yet.
    """
    chooser = rng or random.Random()

    def _texts(rows: Sequence[Lemma]) -> List[str]:
        return [row.lemma_text for row in rows if row.lemma_text]

    at_level = _texts(
        session.query(Lemma)
        .filter(Lemma.difficulty_level == target_level, Lemma.guid.isnot(None))
        .all()
    )
    below_level = _texts(
        session.query(Lemma)
        .filter(
            Lemma.difficulty_level < target_level,
            Lemma.difficulty_level >= 1,
            Lemma.guid.isnot(None),
        )
        .all()
    )

    target_quota = int(sample_size * TARGET_LEVEL_SHARE)
    picked_at_level = chooser.sample(at_level, min(target_quota, len(at_level)))
    remaining = sample_size - len(picked_at_level)
    picked_below = chooser.sample(below_level, min(remaining, len(below_level)))

    # Top up from whichever pool still has words when the other ran dry.
    combined = picked_at_level + picked_below
    if len(combined) < sample_size:
        leftovers = [w for w in at_level + below_level if w not in set(combined)]
        chooser.shuffle(leftovers)
        combined.extend(leftovers[: sample_size - len(combined)])

    return combined


def build_scene_prompt(
    request: SceneRequest,
    *,
    encouraged_words: Sequence[str],
    known_names: Sequence[str] = (),
) -> str:
    """Render the scene prompt template.

    Args:
        request: The validated scene request.
        encouraged_words: Level-appropriate vocabulary to offer.
        known_names: Names already in the database, offered so repeat casting
            reuses an existing entry instead of minting "Georg" beside "George".

    Returns:
        The formatted prompt text.
    """
    template = util.prompt_loader.get_prompt(PROMPT_CATEGORY, PROMPT_TYPE)

    vocabulary_block = (
        ", ".join(encouraged_words)
        if encouraged_words
        else "(no curated vocabulary available yet -- use ordinary everyday words)"
    )
    names_block = (
        ", ".join(known_names)
        if known_names
        else "(none yet -- choose ordinary, easy-to-pronounce names)"
    )
    notes_block = f"\nAdditional direction: {request.notes.strip()}\n" if request.notes else ""

    return template.format(
        scene=request.scene.strip(),
        target_level=request.target_level,
        num_turns=request.num_turns,
        encouraged_words=vocabulary_block,
        known_names=names_block,
        notes=notes_block,
    )


def build_scene_context() -> str:
    """Return the system context for scene generation."""
    return util.prompt_loader.get_context(PROMPT_CATEGORY, PROMPT_TYPE)


def build_scene_schema() -> Schema:
    """Return the structured-output schema for a generated scene."""
    return Schema(
        name="DialogScene",
        description="A short dialog acting out a described scene, for language learners",
        properties={
            "title": SchemaProperty(
                "string", "Short title naming the scene, e.g. 'Buying tomatoes'"
            ),
            "theme": SchemaProperty(
                "string",
                "One-word topic area, e.g. 'shopping', 'medical', 'travel'",
                required=False,
            ),
            "turns": SchemaProperty(
                "array",
                "The dialog, one entry per spoken turn, in order",
                items={
                    "type": "object",
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "description": "Who is speaking: a name from the cast, or a role like 'Clerk'",
                        },
                        "sentences": {
                            "type": "array",
                            "description": (
                                "What they say, one array entry per sentence. Split on "
                                "sentence boundaries; never put two sentences in one entry. "
                                "A turn is usually one or two sentences."
                            ),
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["speaker", "sentences"],
                },
            ),
            "cast": SchemaProperty(
                "array",
                "Every proper name used anywhere in the dialog, including speakers",
                required=False,
                items={
                    "type": "object",
                    "properties": {
                        "name_text": {
                            "type": "string",
                            "description": "The name as written, e.g. 'George'",
                        },
                        "kind": {
                            "type": "string",
                            "description": (
                                "What kind of name: given_name, family_name, full_name, "
                                "place, organization, brand, animal, other"
                            ),
                        },
                        "gender": {
                            "type": "string",
                            "description": "masculine, feminine, or neutral; omit for non-people",
                        },
                        "role": {
                            "type": "string",
                            "description": "This character's role in the scene, e.g. 'the shopper'",
                        },
                    },
                    "required": ["name_text", "kind"],
                },
            ),
        },
    )


def parse_scene_response(
    data: Dict[str, Any],
    *,
    request: SceneRequest,
    encouraged_words: Sequence[str] = (),
    source_model: Optional[str] = None,
) -> SceneDraft:
    """Turn the LLM's structured reply into a :class:`SceneDraft`.

    Turns missing a speaker or text are dropped rather than stored empty: an
    empty line would become a Sentence row with no translation text.

    Args:
        data: The structured data from the LLM response.
        request: The originating request (carries scene and level).
        encouraged_words: The vocabulary that was offered, recorded on the draft.
        source_model: Model that produced the reply.

    Returns:
        The parsed draft.

    Raises:
        ValueError: If the reply contains no usable turns.
    """
    raw_turns = data.get("turns") or []
    turns: List[SceneTurn] = []
    for index, raw_turn in enumerate(raw_turns):
        if not isinstance(raw_turn, dict):
            logger.debug("Skipping non-object turn at index %d: %r", index, raw_turn)
            continue
        sentences = _turn_sentences(raw_turn, index)
        speaker = str(raw_turn.get("speaker") or "").strip()
        if not sentences:
            logger.debug("Skipping turn %d with no usable text", index)
            continue
        turns.append(SceneTurn(speaker=speaker or _fallback_speaker(index), sentences=sentences))

    if not turns:
        raise ValueError("The generated scene contained no usable dialog turns")

    cast: List[CastMember] = []
    for raw_member in data.get("cast") or []:
        if not isinstance(raw_member, dict):
            continue
        name_text = str(raw_member.get("name_text") or "").strip()
        if not name_text:
            continue
        member = CastMember(
            name_text=name_text,
            kind=str(raw_member.get("kind") or "given_name").strip(),
            gender=(str(raw_member.get("gender")).strip() if raw_member.get("gender") else None),
            role=(str(raw_member.get("role")).strip() if raw_member.get("role") else None),
        ).normalized()
        cast.append(member)

    title = str(data.get("title") or "").strip() or request.scene.strip()[:120]
    theme = str(data.get("theme") or "").strip() or None

    return SceneDraft(
        title=title,
        theme=theme,
        turns=turns,
        cast=cast,
        scene=request.scene.strip(),
        target_level=request.target_level,
        source_model=source_model,
        encouraged_words=list(encouraged_words),
    )


def _turn_sentences(raw_turn: Dict[str, Any], index: int) -> List[str]:
    """Extract one turn's sentences from either reply shape.

    The current schema asks for ``sentences`` as a list. Two things can still
    arrive: an older or malformed reply carrying a single ``text`` string, and a
    ``sentences`` list whose entries each hold more than one sentence. Both are
    handled by running the sentence splitter over whatever came back, so the
    splitter acts as a normalizer rather than a second code path -- which also
    keeps it exercised.

    Args:
        raw_turn: One entry of the reply's ``turns`` array.
        index: Position of the turn, for logging.

    Returns:
        The turn's sentences, in order; empty when the turn said nothing.
    """
    # Imported here rather than at module scope: the splitter is the fallback,
    # and the genys agent pulls in the document-ingestion stack.
    from agents.genys.agent import GenysAgent

    raw_sentences = raw_turn.get("sentences")
    if isinstance(raw_sentences, list):
        candidates = [str(entry) for entry in raw_sentences if str(entry or "").strip()]
    else:
        candidates = []

    if not candidates:
        text = str(raw_turn.get("text") or "").strip()
        if not text:
            return []
        logger.info("Turn %d has no 'sentences' list; splitting its 'text' instead", index)
        candidates = [text]

    sentences: List[str] = []
    for candidate in candidates:
        parts = GenysAgent.split_sentences(candidate, GENERATION_LANG)
        # split_sentences returns [] only for empty input, which is filtered
        # above; keep the original as a single sentence if it ever does.
        sentences.extend(parts or [candidate.strip()])
    return [sentence for sentence in sentences if sentence]


def _fallback_speaker(index: int) -> str:
    """Speaker label used when the model omitted one (alternating A/B)."""
    return "A" if index % 2 == 0 else "B"


def generate_scene(
    session: Session,
    request: SceneRequest,
    config: DataSourceConfig,
    *,
    known_names: Sequence[str] = (),
    client: Optional[UnifiedLLMClient] = None,
) -> SceneDraft:
    """Generate one dialog for a scene at a target level.

    Args:
        session: Database session, used only to sample encouraged vocabulary.
        request: What to generate.
        config: Data source configuration (carries the model and API keys).
        known_names: Names already registered, offered for reuse.
        client: Optional pre-built client, mainly for tests.

    Returns:
        The generated draft.

    Raises:
        ValueError: If the request is invalid or the reply had no usable turns.
        RuntimeError: If the LLM returned no structured data.
    """
    request.validate()

    model = request.model or config.model
    if not model:
        raise ValueError("Scene generation requires a model (set config.model or request.model)")

    encouraged_words = sample_encouraged_vocabulary(session, request.target_level)
    prompt = build_scene_prompt(request, encouraged_words=encouraged_words, known_names=known_names)

    llm_client = client or UnifiedLLMClient.from_config(config)
    response = llm_client.generate_chat(
        prompt=prompt,
        model=model,
        context=build_scene_context(),
        json_schema=build_scene_schema(),
    )
    if not response.structured_data:
        raise RuntimeError(f"Model {model} returned no structured data for the scene")

    return parse_scene_response(
        response.structured_data,
        request=request,
        encouraged_words=encouraged_words,
        source_model=model,
    )
