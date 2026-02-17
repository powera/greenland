#!/usr/bin/python3

"""Scoring helpers for the synonyms benchmark."""

import re
from typing import Any, Dict, List, Set


def normalize_synonym(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = cleaned.replace("\u2019", "'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .,!?:;\"'`()[]{}")
    return cleaned


def extract_candidate_synonyms(response: Any) -> List[str]:
    if isinstance(response, dict):
        values = response.get("synonyms", [])
        if isinstance(values, list):
            return [str(item) for item in values]
        if isinstance(values, str):
            return [values]
        return []

    text = str(response)
    return [part for part in re.split(r"[,;\n]", text) if part.strip()]


def score_synonyms_response(question_data: Dict, response: Any) -> float:
    """Return partial-credit score in [0, 100]."""
    correct_answer = question_data.get("correct_answer", {})

    mandatory: Set[str] = {
        normalize_synonym(item)
        for item in correct_answer.get("mandatory_synonyms", [])
        if isinstance(item, str)
    }
    optional: Set[str] = {
        normalize_synonym(item)
        for item in correct_answer.get("optional_synonyms", [])
        if isinstance(item, str)
    }

    if not mandatory and not optional:
        # Backward compatibility with older shape.
        optional = {
            normalize_synonym(item)
            for item in correct_answer.get("synonyms", [])
            if isinstance(item, str)
        }

    predicted: Set[str] = {
        normalize_synonym(item)
        for item in extract_candidate_synonyms(response)
        if isinstance(item, str) and item.strip()
    }

    expected = mandatory | optional
    if not expected:
        return 100.0 if not predicted else max(0.0, 100.0 - (20.0 * len(predicted)))

    mandatory_recall = len(predicted & mandatory) / len(mandatory) if mandatory else 1.0
    optional_recall = len(predicted & optional) / len(optional) if optional else 1.0
    precision = len(predicted & expected) / len(predicted) if predicted else 0.0

    weighted_components = []
    if mandatory:
        weighted_components.append((0.75, mandatory_recall))
    if optional:
        weighted_components.append((0.20, optional_recall))
    weighted_components.append((0.05, precision))

    total_weight = sum(weight for weight, _ in weighted_components)
    raw = sum(weight * value for weight, value in weighted_components) / total_weight
    return round(raw * 100.0, 2)
