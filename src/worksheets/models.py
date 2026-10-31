"""Renderer-independent English worksheet content."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    source_id: str
    text: str
    definition: str
    emoji: str = ""


@dataclass(frozen=True)
class FormEntry:
    """A base word and the inflected forms a question asks for, in order."""

    source_id: str
    base: str
    forms: tuple[str, ...]
    # Sense disambiguation, needed where homographs inflect differently
    # (hang/hanged for execution, hang/hung for suspension).
    clue: str = ""


@dataclass(frozen=True)
class FamilyMember:
    """One word of a derivational family, with the part of speech shown as its label."""

    source_id: str
    text: str
    pos_type: str
    definition: str


@dataclass(frozen=True)
class Question:
    source_id: str
    prompt: str
    clue: str
    answer: str


@dataclass(frozen=True)
class Worksheet:
    title: str
    instructions: str
    questions: tuple[Question, ...]
    choices: tuple[str, ...] = ()
    emoji_clues: bool = False
