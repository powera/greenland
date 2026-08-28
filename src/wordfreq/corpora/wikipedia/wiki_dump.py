#!/usr/bin/python3

"""Random access into a Wikimedia dump snapshot, by page title.

The source for the ``wiki_vital`` corpus.  Unlike Gutenberg books and CAP
opinions, which are downloaded per document, Wikipedia is taken from a single
downloaded snapshot -- a ``pages-articles-multistream.xml.bz2`` dump and its
``-index.txt`` companion, located by :data:`constants.WIKI_CORPUS_BASE_PATH`.
Nothing here touches the network: the snapshot is fetched by hand, and the
builder reads whatever is on disk.

The dump is one large bz2 file, but it is a *multistream* one: it concatenates
independently compressed ~2MB blocks, so a block holding a given page can be
seeked to and decompressed alone.  The index file records which byte offset
each page lives at.  :meth:`WikiLoader.build_offset_index` converts that index
into SQLite databases sharded by the MD5 of the page title, which optimizes for
direct title lookups rather than title-range scans; the builder then asks for
its thousand articles by name.

This module predates the rest of the corpora package and is left as it was
found: the paths still come from module-level ``constants`` rather than a
config object, and the index build has had no exercise recently.  It is the
one part of the Wikipedia pipeline that needs a snapshot on hand to run.
"""

import bz2
import hashlib
import os
import sqlite3
import xml.dom.minidom
from typing import Optional, Tuple

import constants

# Two-digit files (maybe)
HEX_DIGITS = "0123456789abcdef"
ALL_KEYS = [a + b for a in HEX_DIGITS for b in HEX_DIGITS]


class WikiLoader:
    """Class for accessing and indexing Wikimedia dump files."""

    def __init__(self, corpus: str = "enwiki", offset_dir: Optional[str] = None):
        """
        Initialize a WikiLoader for the specified corpus.

        Args:
            corpus: Corpus identifier (e.g., "enwiki" for English Wikipedia)
            offset_dir: Where the sharded SQLite index lives; see
                :meth:`set_corpus_base`.
        """
        self.corpus = corpus
        self.corpus_prefix = constants.WIKI_CORPUS_PREFIX
        self.schema_file = constants.WIKI_INDEX_SCHEMA_PATH
        self.set_corpus_base(
            constants.WIKI_CORPUS_BASE_PATH, constants.WIKI_CORPUS_PREFIX, offset_dir
        )

    def set_corpus_base(
        self,
        corpus_base: str,
        corpus_prefix: Optional[str] = None,
        offset_dir: Optional[str] = None,
    ) -> None:
        """Point this loader at a snapshot directory.

        Args:
            corpus_base: Directory holding the dump and its index file.
            corpus_prefix: Dump filename prefix (e.g. ``enwiki-20220501``).
                Keeps the current prefix when omitted.
            offset_dir: Where the sharded SQLite index lives.  Defaults to an
                ``offset`` subdirectory of ``corpus_base``.

                Override this **while building** when the snapshot sits on an
                **exFAT** drive, which is the usual case for a 21GB dump on an
                external disk: exFAT lacks the byte-range locking SQLite needs
                to write, so ``build_offset_index`` fails part-way with
                "attempt to write a readonly database" even though ordinary
                file writes to the same directory succeed.  Build the index on
                local disk, then copy it beside the dump.

                Reading is unaffected -- an exFAT-hosted index opens and
                queries normally, so the finished index can live on the drive
                with the dump and needs no override to be used.
        """
        self.corpus_base = corpus_base
        if corpus_prefix is not None:
            self.corpus_prefix = corpus_prefix

        self.offset_dir = offset_dir or os.path.join(self.corpus_base, "offset")
        self.dump_file = os.path.join(
            self.corpus_base, f"{self.corpus_prefix}-pages-articles-multistream.xml.bz2"
        )
        self.index_file = os.path.join(
            self.corpus_base, f"{self.corpus_prefix}-pages-articles-multistream-index.txt"
        )

    def is_indexed(self) -> bool:
        """Whether :meth:`build_offset_index` has been run for this snapshot.

        Checks for the shard databases rather than the dump, because reading a
        page needs both and only the index is something this class creates.
        """
        return all(os.path.exists(self._get_db_path(key)) for key in ALL_KEYS)

    @staticmethod
    def _shard_for_title(title: str) -> str:
        """
        Determine the shard for a given page title using MD5 hash.

        Args:
            title: The page title

        Returns:
            Two hex characters representing the shard
        """
        return hashlib.md5(bytes(title, "utf-8")).hexdigest()[:2]

    def _get_db_path(self, shard: str) -> str:
        """
        Get the path to a specific shard's SQLite database.

        Args:
            shard: The shard identifier (hex digit)

        Returns:
            Full path to the SQLite database
        """
        return os.path.join(self.offset_dir, f"{self.corpus_prefix}-{shard}.sqlite")

    def build_offset_index(self, batch_size: int = 500000) -> None:
        """Build SQLite indexes using the flat-file approach for 20M entries."""
        # Ensure directories exist
        os.makedirs(self.offset_dir, exist_ok=True)
        temp_dir = os.path.join(self.offset_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Phase 1: Parse index file and write to shard text files
        shard_files = {}
        shard_writers = {}

        try:
            # Open output files for each shard
            for key in ALL_KEYS:
                shard_path = os.path.join(temp_dir, f"shard_{key}.txt")
                shard_files[key] = open(shard_path, "w", buffering=8 * 1024 * 1024)
                shard_writers[key] = shard_files[key].write

            # Parse the index file
            page_count = 0
            current_offset = -1
            current_titles: list[tuple[str, str]] = []

            with open(self.index_file, "r", buffering=8 * 1024 * 1024) as f:
                for line in f:
                    page_count += 1

                    try:
                        offset_str, pid, pname = line.split(":", 2)
                        offset = int(offset_str)
                        pname = pname.strip()
                    except (ValueError, IndexError):
                        continue

                    # Process offset changes
                    if offset != current_offset and current_offset > 0:
                        # Calculate read size
                        read_size = offset - current_offset

                        # Write entries to appropriate shard files
                        for title, page_id in current_titles:
                            if not title or len(title) > 191:
                                continue

                            shard = self._shard_for_title(title)
                            # Format: title|offset|read_size|page_id
                            shard_writers[shard](
                                f"{title}|{current_offset}|{read_size}|{page_id}\n"
                            )

                        # Reset for new offset
                        current_titles = []

                    # Record for next offset change
                    current_offset = offset
                    current_titles.append((pname, pid))

                    # Periodic status update
                    if page_count % 1000000 == 0:
                        print(f"{page_count} pages processed (phase 1)")

            # Process the last batch
            if current_titles and current_offset > 0:
                for title, page_id in current_titles:
                    if not title or len(title) > 191:
                        continue

                    shard = self._shard_for_title(title)
                    # Assume fixed read size for the last block
                    read_size = 1024 * 1024  # 1MB should be enough for last block
                    shard_writers[shard](f"{title}|{current_offset}|{read_size}|{page_id}\n")

        finally:
            # Close all shard files
            for file in shard_files.values():
                file.close()

        print(f"Phase 1 complete. Processed {page_count} pages.")

        # Phase 2: Convert each shard file to SQLite
        with open(self.schema_file) as f:
            schema = f.read()

        for key in ALL_KEYS:
            print(f"Converting shard {key} to SQLite...")

            # Create and prepare the database
            db_path = self._get_db_path(key)
            conn = sqlite3.connect(db_path)
            conn.executescript(schema)

            # Set performance parameters
            conn.execute("PRAGMA journal_mode = OFF")  # Disable journaling for bulk load
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            conn.execute("PRAGMA page_size = 8192")

            # Process the shard file in batches
            shard_path = os.path.join(temp_dir, f"shard_{key}.txt")
            entries = []

            with open(shard_path, "r") as f:
                conn.execute("BEGIN TRANSACTION")

                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) != 4:
                        continue

                    title, offset_str, read_size_str, page_id_str = parts
                    entries.append((title, int(offset_str), int(read_size_str), int(page_id_str)))

                    if len(entries) >= batch_size:
                        conn.executemany(
                            "INSERT OR IGNORE INTO offsets(key, offset, offset_readsize, page_id) VALUES (?, ?, ?, ?)",
                            entries,
                        )
                        entries = []

                # Insert any remaining entries
                if entries:
                    conn.executemany(
                        "INSERT OR IGNORE INTO offsets(key, offset, offset_readsize, page_id) VALUES (?, ?, ?, ?)",
                        entries,
                    )

                conn.execute("COMMIT")

            # Optimize the database
            conn.execute("PRAGMA journal_mode = WAL")  # Reset to WAL for normal operation
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("CREATE INDEX IF NOT EXISTS offsets_key_idx ON offsets(key)")
            conn.execute("ANALYZE")
            conn.close()

            # Remove the temporary file
            os.unlink(shard_path)

        # Remove the temporary directory if it's empty
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

        print("Index build complete.")

    def get_offset_for_page(self, page_name: str) -> Tuple[int, int]:
        """
        Get the file offset for a specific page.

        Args:
            page_name: The title of the wiki page

        Returns:
            Tuple of (offset, read_size)

        Raises:
            ValueError: If the page is not found in the index
        """
        shard = self._shard_for_title(page_name)
        db_path = self._get_db_path(shard)

        try:
            db = sqlite3.connect(db_path)
            cur = db.cursor()
            result = cur.execute(
                "SELECT offset, offset_readsize FROM offsets WHERE key=?", [page_name]
            )
            row = result.fetchone()

            if not row:
                raise ValueError(f"Page not found in index: {page_name}")

            return row[0], row[1]
        finally:
            cur.close()
            db.close()

    def get_root_node_from_file(self, page_name: str) -> xml.dom.minidom.Element:
        """
        Get the DOM root node for a specific page.

        Args:
            page_name: The title of the wiki page

        Returns:
            The DOM root node for the page

        Raises:
            ValueError: If the page is not found
            FileNotFoundError: If the dump file is not found
        """
        try:
            offset, offset_read_size = self.get_offset_for_page(page_name)
        except ValueError:
            raise ValueError(f"Page not found in index: {page_name}")

        # Read the section of file containing the XML for the page
        try:
            with open(self.dump_file, "rb") as f:
                f.seek(offset)
                decompressor = bz2.BZ2Decompressor()
                results = decompressor.decompress(f.read(offset_read_size))
                xmldoc = xml.dom.minidom.parseString(b"<wiki>" + results + b"</wiki>")
        except FileNotFoundError:
            raise FileNotFoundError(f"Dump file not found: {self.dump_file}")
        except Exception as e:
            raise RuntimeError(f"Error reading page {page_name}: {e}")

        try:
            root_node = self._locate_root_node(xmldoc, page_name)
            return root_node
        except Exception:
            raise ValueError(f"Could not locate page content for {page_name}")

    def get_text_from_page(self, page_name: str) -> str:
        """
        Get the text content for a specific wiki page.

        Args:
            page_name: The title of the wiki page

        Returns:
            The text content of the page

        Raises:
            ValueError: If the page is not found or its content cannot be extracted
        """
        try:
            # The root node contains page name, id, and a recent revision
            root_node = self.get_root_node_from_file(page_name)

            # The "revision" tag contains the revision ID, time, and text
            revisions = root_node.getElementsByTagName("revision")
            if not revisions:
                raise ValueError(f"No revision found for page {page_name}")

            revision = revisions[0]
            text_nodes = revision.getElementsByTagName("text")

            if not text_nodes or not text_nodes[0].childNodes:
                return ""

            first_child = text_nodes[0].childNodes[0]
            if first_child.nodeValue is None:
                return ""
            return first_child.nodeValue  # type: ignore[no-any-return]

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Error extracting text from {page_name}: {str(e)}")

    def _locate_root_node(
        self, xmldoc: xml.dom.minidom.Document, page_name: str
    ) -> xml.dom.minidom.Element:
        """
        Find the correct page node in an XML document with multiple pages.

        Args:
            xmldoc: The XML document
            page_name: The title of the wiki page

        Returns:
            The root node for the specified page

        Raises:
            ValueError: If the page is not found in the XML
        """
        titles = xmldoc.getElementsByTagName("title")

        for tag in titles:
            if (
                tag.firstChild
                and hasattr(tag.firstChild, "wholeText")
                and tag.firstChild.wholeText == page_name
            ):
                parent = tag.parentNode
                if isinstance(parent, xml.dom.minidom.Element):
                    return parent

        raise ValueError(f"Page {page_name} not found in XML document")
