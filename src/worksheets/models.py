"""Renderer-independent English worksheet content."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    source_id: str
    text: str
    definition: str
    emoji: str = ""


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
