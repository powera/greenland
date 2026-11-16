"""Tests for OANC archive member selection and document cleaning.

The archive carries a macOS resource-fork file (``._Article247_3.txt``) beside
every primary text; extracting those doubled the Slate file count and fed
binary junk to the tokenizer, so their exclusion is asserted in both places
that read file names.
"""

from pathlib import Path, PurePosixPath

from wordfreq.corpora.download_oanc import member_target
from wordfreq.corpora.oanc_text import clean_document, iter_documents


def test_member_target_keeps_requested_subcorpus_text() -> None:
    name = "OANC-GrAF/data/written_1/journal/slate/6/Article247_720.txt"
    assert member_target(name, ["slate"]) == PurePosixPath("slate/6/Article247_720.txt")


def test_member_target_skips_annotations_other_subcorpora_and_resource_forks() -> None:
    base = "OANC-GrAF/data/written_1/journal/slate/6/"
    assert member_target(base + "Article247_720-hepple.xml", ["slate"]) is None
    assert member_target(base + "._Article247_720.txt", ["slate"]) is None
    assert member_target("OANC-GrAF/data/written_1/journal/verbatim/a.txt", ["slate"]) is None


def test_clean_document_drops_headline_and_rejoins_wrapped_lines() -> None:
    raw = (
        "            Slobodan But Surely?\n\n"
        "            The New York Times\nand Los\nAngeles Times lead.\n\n"
        "            Second paragraph.\n"
    )
    assert clean_document(raw) == (
        "The New York Times and Los Angeles Times lead.\n\nSecond paragraph."
    )


def test_iter_documents_skips_resource_forks_and_short_texts(tmp_path: Path) -> None:
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "A.txt").write_text("Title\n\nA long enough body of text.\n")
    (tmp_path / "1" / "._A.txt").write_text("Title\n\njunk resource fork body\n")
    (tmp_path / "1" / "B.txt").write_text("Title\n\nShort.\n")
    documents = list(iter_documents(tmp_path, min_chars=10))
    assert [document.slug for document in documents] == ["1/A"]
