#!/usr/bin/env python3
"""Extract hardcoded Barsukas template strings into STRINGS references.

NOTE: Keep this module self-contained and portable.
Do not import application modules from the rest of ``src/`` here.
"""

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "barsukas" / "templates"
STRINGS_ROOT = REPO_ROOT / "strings" / "barsukas"
ATTRIBUTE_ALLOWLIST = {
    "title",
    "placeholder",
    "aria-label",
    "alt",
    "value",
    "label",
    "data-bs-original-title",
}
NAMESPACE_ALIAS = {
    "sync_release": "sync",
    "parts_of_speech": "common.linguistics",
}
ENTITY_PATTERN = re.compile(r"^(?:&[a-zA-Z]+;|&#\d+;|&#x[0-9a-fA-F]+;)+$")
JINJA_OR_COMMENT_PATTERN = re.compile(r"<!--.*?-->|\{\{.*?\}\}|\{\%.*?\%\}|\{\#.*?\#\}", re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>", re.DOTALL)
ATTRIBUTE_PATTERN = re.compile(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", re.DOTALL)


@dataclass(frozen=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True)
class Replacement:
    start: int
    end: int
    replacement_text: str
    original_text: str
    namespace: str
    string_key: str


@dataclass
class CatalogUpdateStats:
    reused_common_count: int = 0
    new_key_count: int = 0
    collisions_resolved: int = 0


class CatalogState:
    def __init__(self, strings_root: Path) -> None:
        self.strings_root = strings_root
        self.catalogs: dict[str, dict[str, str]] = {}
        self.reverse_lookup: dict[str, list[tuple[str, str]]] = {}
        self.new_keys: dict[str, set[str]] = {}
        self.namespace_dirs: set[str] = set()
        self._load_catalogs()

    def _load_catalogs(self) -> None:
        self.strings_root.mkdir(parents=True, exist_ok=True)
        for en_path in sorted(self.strings_root.rglob("en.json")):
            namespace_dir = en_path.parent
            if not namespace_dir.is_dir():
                continue
            try:
                relative_parts = namespace_dir.relative_to(self.strings_root).parts
            except ValueError:
                continue
            if not relative_parts:
                continue
            namespace = ".".join(relative_parts)
            self.namespace_dirs.add(namespace)
            with en_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            catalog = {str(key): str(value) for key, value in loaded.items()}
            self.catalogs[namespace] = catalog
            for string_key, english_text in catalog.items():
                normalized = normalize_for_lookup(english_text)
                if normalized:
                    self.reverse_lookup.setdefault(normalized, []).append((namespace, string_key))

    def ensure_namespace(self, namespace: str) -> None:
        if namespace in self.catalogs:
            return
        self.catalogs[namespace] = {}
        self.new_keys.setdefault(namespace, set())
        self.namespace_dirs.add(namespace)

    def resolve_or_create_key(
        self,
        normalized_text: str,
        original_text: str,
        preferred_namespace: str,
        stats: CatalogUpdateStats,
    ) -> tuple[str, str]:
        existing_locations = self.reverse_lookup.get(normalized_text, [])
        if existing_locations:
            common_match = next((item for item in existing_locations if item[0] == "common"), None)
            if common_match is not None:
                stats.reused_common_count += 1
                return common_match
            return sorted(existing_locations)[0]

        namespace = preferred_namespace
        self.ensure_namespace(namespace)
        generated_key, collision_happened = generate_unique_key(
            namespace, original_text, self.catalogs
        )
        if collision_happened:
            stats.collisions_resolved += 1
        self.catalogs[namespace][generated_key] = original_text
        self.reverse_lookup.setdefault(normalized_text, []).append((namespace, generated_key))
        self.new_keys.setdefault(namespace, set()).add(generated_key)
        stats.new_key_count += 1
        return (namespace, generated_key)

    def write(self) -> None:
        for namespace in sorted(self.namespace_dirs):
            namespace_dir = self.strings_root.joinpath(*namespace.split("."))
            namespace_dir.mkdir(parents=True, exist_ok=True)
            english_catalog = self.catalogs.get(namespace, {})
            english_sorted = {
                string_key: english_catalog[string_key] for string_key in sorted(english_catalog)
            }

            with (namespace_dir / "en.json").open("w", encoding="utf-8") as en_handle:
                json.dump(english_sorted, en_handle, ensure_ascii=False, indent=2)
                en_handle.write("\n")

            lt_path = namespace_dir / "lt.json"
            if lt_path.exists():
                with lt_path.open("r", encoding="utf-8") as lt_handle:
                    loaded_lt = json.load(lt_handle)
                lithuanian_catalog = {str(key): str(value) for key, value in loaded_lt.items()}
            else:
                lithuanian_catalog = {}

            for string_key, english_text in english_sorted.items():
                if string_key not in lithuanian_catalog:
                    lithuanian_catalog[string_key] = english_text
            lt_sorted = {
                string_key: lithuanian_catalog[string_key]
                for string_key in sorted(lithuanian_catalog)
            }
            with lt_path.open("w", encoding="utf-8") as lt_handle:
                json.dump(lt_sorted, lt_handle, ensure_ascii=False, indent=2)
                lt_handle.write("\n")


def normalize_for_lookup(text: str) -> str:
    return " ".join(text.strip().split())


def should_ignore_text(normalized_text: str) -> bool:
    if not normalized_text:
        return True
    if "{{" in normalized_text or "{%" in normalized_text:
        return True
    if ENTITY_PATTERN.fullmatch(normalized_text):
        return True
    if re.fullmatch(r"[\d\s.,:/+\-()%]+", normalized_text):
        return True
    if re.fullmatch(r"[_\W]+", normalized_text, flags=re.UNICODE):
        return True
    if not re.search(r"[A-Za-z]", normalized_text):
        return True
    if normalized_text.replace("bi", "").replace("-", "").strip() == "":
        return True
    return False


def get_template_namespace(template_path: Path) -> str:
    relative_path = template_path.relative_to(TEMPLATES_ROOT)
    root_part = relative_path.parts[0] if len(relative_path.parts) > 1 else "common"
    return NAMESPACE_ALIAS.get(root_part, root_part)


def generate_key_seed(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.casefold()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not cleaned:
        return "text"
    if cleaned[0].isdigit():
        return f"text_{cleaned}"
    return cleaned


def generate_unique_key(
    namespace: str,
    english_text: str,
    catalogs: dict[str, dict[str, str]],
) -> tuple[str, bool]:
    namespace_catalog = catalogs.setdefault(namespace, {})
    base_seed = generate_key_seed(english_text)
    if base_seed in namespace_catalog and namespace_catalog[base_seed] == english_text:
        return (base_seed, False)
    if base_seed not in namespace_catalog:
        return (base_seed, False)

    index = 2
    while True:
        candidate_key = f"{base_seed}_{index}"
        if candidate_key not in namespace_catalog:
            return (candidate_key, True)
        if namespace_catalog[candidate_key] == english_text:
            return (candidate_key, True)
        index += 1


def find_protected_spans(content: str) -> list[Span]:
    spans = [
        Span(match.start(), match.end()) for match in JINJA_OR_COMMENT_PATTERN.finditer(content)
    ]
    if not spans:
        return []
    spans.sort(key=lambda current: current.start)
    merged: list[Span] = []
    for current_span in spans:
        if not merged or current_span.start > merged[-1].end:
            merged.append(current_span)
            continue
        merged[-1] = Span(merged[-1].start, max(merged[-1].end, current_span.end))
    return merged


def has_overlap(candidate: Span, protected_spans: list[Span]) -> bool:
    for protected in protected_spans:
        if candidate.start >= protected.end:
            continue
        if candidate.end <= protected.start:
            break
        return True
    return False


def split_unprotected_segments(segment_span: Span, protected_spans: list[Span]) -> list[Span]:
    slices: list[Span] = []
    cursor = segment_span.start
    for protected in protected_spans:
        if protected.end <= segment_span.start:
            continue
        if protected.start >= segment_span.end:
            break
        if protected.start > cursor:
            slices.append(Span(cursor, min(protected.start, segment_span.end)))
        cursor = max(cursor, protected.end)
        if cursor >= segment_span.end:
            break
    if cursor < segment_span.end:
        slices.append(Span(cursor, segment_span.end))
    return [entry for entry in slices if entry.start < entry.end]


def build_text_replacement(
    content: str,
    span: Span,
    namespace: str,
    catalog_state: CatalogState,
    stats: CatalogUpdateStats,
) -> Replacement | None:
    original_segment = content[span.start : span.end]
    trimmed = original_segment.strip()
    normalized = normalize_for_lookup(trimmed)
    if should_ignore_text(normalized):
        return None

    leading_length = len(original_segment) - len(original_segment.lstrip())
    trailing_length = len(original_segment) - len(original_segment.rstrip())
    leading = original_segment[:leading_length]
    trailing = (
        original_segment[len(original_segment) - trailing_length :] if trailing_length else ""
    )

    selected_namespace, selected_key = catalog_state.resolve_or_create_key(
        normalized_text=normalized,
        original_text=trimmed,
        preferred_namespace=namespace,
        stats=stats,
    )
    expression = f"{{{{ STRINGS.{selected_namespace}.{selected_key} }}}}"
    return Replacement(
        start=span.start,
        end=span.end,
        replacement_text=f"{leading}{expression}{trailing}",
        original_text=trimmed,
        namespace=selected_namespace,
        string_key=selected_key,
    )


def plan_template_replacements(
    template_path: Path,
    catalog_state: CatalogState,
    stats: CatalogUpdateStats,
) -> list[Replacement]:
    content = template_path.read_text(encoding="utf-8")
    protected_spans = find_protected_spans(content)
    namespace = get_template_namespace(template_path)

    planned: list[Replacement] = []

    for tag_match in TAG_PATTERN.finditer(content):
        tag_span = Span(tag_match.start(), tag_match.end())
        if has_overlap(tag_span, protected_spans):
            continue
        tag_text = tag_match.group(0)
        if tag_text.startswith("<!--"):
            continue
        for attr_match in ATTRIBUTE_PATTERN.finditer(tag_text):
            attribute_name = attr_match.group(1).casefold()
            if attribute_name not in ATTRIBUTE_ALLOWLIST:
                continue
            attribute_value = attr_match.group(3)
            normalized = normalize_for_lookup(attribute_value)
            if should_ignore_text(normalized):
                continue
            if "{{" in attribute_value or "{%" in attribute_value:
                continue
            value_start = tag_match.start() + attr_match.start(3)
            value_end = tag_match.start() + attr_match.end(3)
            selected_namespace, selected_key = catalog_state.resolve_or_create_key(
                normalized_text=normalized,
                original_text=attribute_value.strip(),
                preferred_namespace=namespace,
                stats=stats,
            )
            planned.append(
                Replacement(
                    start=value_start,
                    end=value_end,
                    replacement_text=f"{{{{ STRINGS.{selected_namespace}.{selected_key} }}}}",
                    original_text=attribute_value.strip(),
                    namespace=selected_namespace,
                    string_key=selected_key,
                )
            )

    for text_match in re.finditer(r">([^<]+)<", content, flags=re.DOTALL):
        candidate_span = Span(text_match.start(1), text_match.end(1))
        for piece in split_unprotected_segments(candidate_span, protected_spans):
            replacement = build_text_replacement(
                content=content,
                span=piece,
                namespace=namespace,
                catalog_state=catalog_state,
                stats=stats,
            )
            if replacement is not None:
                planned.append(replacement)

    deduped_by_range: dict[tuple[int, int], Replacement] = {}
    for replacement in planned:
        deduped_by_range[(replacement.start, replacement.end)] = replacement
    return sorted(deduped_by_range.values(), key=lambda item: item.start)


def apply_replacements(content: str, replacements: Iterable[Replacement]) -> str:
    updated = content
    for replacement in sorted(replacements, key=lambda entry: entry.start, reverse=True):
        updated = (
            updated[: replacement.start] + replacement.replacement_text + updated[replacement.end :]
        )
    return updated


def compute_plan() -> tuple[dict[Path, list[Replacement]], CatalogState, CatalogUpdateStats]:
    catalog_state = CatalogState(STRINGS_ROOT)
    stats = CatalogUpdateStats()
    template_plans: dict[Path, list[Replacement]] = {}
    for template_path in sorted(TEMPLATES_ROOT.rglob("*.html")):
        replacements = plan_template_replacements(template_path, catalog_state, stats)
        if replacements:
            template_plans[template_path] = replacements
    return (template_plans, catalog_state, stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Barsukas STRINGS references from hardcoded template text."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="Show planned changes, exit 1 if needed."
    )
    mode.add_argument("--write", action="store_true", help="Apply template and catalog updates.")
    mode.add_argument(
        "--count",
        action="store_true",
        help="Print only the number of pending replacements (for pre-commit hooks).",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    template_plans, catalog_state, stats = compute_plan()

    replacement_total = sum(len(items) for items in template_plans.values())
    change_needed = bool(template_plans or any(catalog_state.new_keys.values()))

    if arguments.count:
        print(replacement_total)
        return 1 if change_needed else 0

    for template_path, replacements in template_plans.items():
        relative_template = template_path.relative_to(REPO_ROOT)
        print(f"{relative_template}: {len(replacements)} replacement(s)")
        for replacement in replacements:
            print(
                f"  - '{replacement.original_text}' -> STRINGS.{replacement.namespace}.{replacement.string_key}"
            )

    for namespace, keys in sorted(catalog_state.new_keys.items()):
        if keys:
            print(f"new keys [{namespace}]: {', '.join(sorted(keys))}")

    print("summary:")
    print(f"  templates changed: {len(template_plans)}")
    print(f"  total replacements: {replacement_total}")
    print(f"  reused common: {stats.reused_common_count}")
    print(f"  new keys: {stats.new_key_count}")
    print(f"  collisions resolved: {stats.collisions_resolved}")

    if arguments.write and change_needed:
        for template_path, replacements in template_plans.items():
            original_content = template_path.read_text(encoding="utf-8")
            updated_content = apply_replacements(original_content, replacements)
            template_path.write_text(updated_content, encoding="utf-8")
        catalog_state.write()

    if arguments.check and change_needed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
