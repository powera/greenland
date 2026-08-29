"""Plain-text extraction from Wikipedia wikitext.

The counterpart of :mod:`wordfreq.corpora.gutenberg_text` and
:mod:`wordfreq.corpora.scotus_text` for article source.  Purely mechanical: no
network, no database.  A stripped article goes through
:func:`wordfreq.corpora.gutenberg_text.analyze_text` unchanged, so the
tokenizer and capitalization analysis are shared with the other two corpora.

**Wikitext is parsed, not regex-stripped.**  Its constructs nest -- a template
argument holds another template, an infobox holds a table holding links --
and a pattern like ``\\{\\{[^}]*\\}\\}`` stops at the *first* ``}}`` it meets,
so on ``{{convert|5|km|{{abbr|mi}}}}`` it consumes through the inner close and
leaves ``}}`` behind as prose.  The earlier version of this corpus was built
that way, which is why template residue reached its word list.  Instead a
character-level tokenizer emits structural tokens (``{{``, ``}}``, ``[[``,
``|``, ``{|``, ``<ref>``) and a block tree consumes them, so every construct
closes where it actually closes.

What each construct contributes to the text:

* **Links** give their display text: ``[[Pablo Picasso|Picasso]]`` yields
  "Picasso", and a bare ``[[Cubism]]`` yields "Cubism".  ``[[File:...]]`` and
  ``[[Image:...]]`` yield nothing -- a caption is written in a different
  register from body prose and is full of photographer credits.
* **Templates** yield nothing, except the few in :data:`RAW_TEMPLATES` that
  wrap running prose rather than generating apparatus.  An infobox is a data
  table, and counting it would put "caption", "align" and "px" into an English
  frequency list.
* **External links** yield nothing -- neither the URL nor its label.
  ``[https://www.bbc.co.uk/news BBC News]`` is citation apparatus, and its
  text is a publisher or "Archived from the original" rather than a sentence.
  A bare URL in prose is stripped too.  Left in, the word tokenizer split
  these on their punctuation: "http" was rank 80 in the wiki_biology corpus,
  with "www", "org", "com", "html", "edu", "php", "gov" and "aspx" behind it.
  A ``[`` with no URL after it is prose ("[sic]") and is kept.
* **References** yield nothing.  ``<ref>`` content is citation apparatus, the
  same material :mod:`wordfreq.corpora.scotus_text` strips from opinions.
* **Tables** yield nothing, for the reason infoboxes do not.
* **Headings** yield nothing.  A section title is a label, not a sentence, and
  counting it would weight "References", "See also" and "History" once per
  article across the whole corpus.
* **Bold and italic markers** are dropped, keeping the words they wrap.
* **HTML tags** are dropped.  A prose tag (``<small>``, ``<sub>``, ``<span>``)
  keeps the text it wraps, as an emphasis marker does; an opaque one
  (``<gallery>``, ``<syntaxhighlight>``) drops its body too, as ``<math>``
  does; ``<nowiki>`` keeps its body as literal text.  The tag name itself
  never reaches the text: left in, ``sub`` and ``sup`` were counted as English
  words 3494 and 1980 times in the wiki_math corpus.
* **HTML comments** yield nothing.

The tokenizer and block model are adapted from the wikitext parser in the slmt
project.
"""

import re
from typing import Dict, List, Optional, Sequence, Set, Union

# Templates whose body is running prose rather than generated apparatus, so
# their text is kept.  "{{lang|fr|coup d'etat}}" and "{{circa|1500}}" appear
# mid-sentence and reading around them would leave a hole in the sentence.
RAW_TEMPLATES = frozenset(["as of", "circa", "lang", "nihongo", "sc"])

# Link namespaces that are media rather than prose.
_MEDIA_PREFIXES = ("File:", "Image:", "Media:")

# URL schemes that make a single "[" an external link rather than punctuation,
# and that mark a bare run of text in prose as a URL.  Wikitext also permits
# a protocol-relative "//host/path".
_URL_PREFIXES = ("http://", "https://", "ftp://", "//", "www.")

# HTML tags whose body is prose: the tag itself is dropped and the text it
# wraps is kept, the way an emphasis marker is.  Without this the tokenizer
# emits the tag verbatim as text and the word tokenizer reads its name as an
# English word -- "sub" was wiki_math's 3494-count entry, "sup" its 1980, and
# "small" (a real word) had 4034 counts in a wiki corpus against ~2000 in a book
# corpus of comparable size.
_PROSE_TAGS = frozenset(
    [
        "abbr",
        "b",
        "big",
        "blockquote",
        "bdi",
        "center",
        "cite",
        "code",
        "data",
        "del",
        "dfn",
        "div",
        "em",
        "font",
        "i",
        "ins",
        "kbd",
        "li",
        "mark",
        "ol",
        "p",
        "poem",
        "q",
        "rb",
        "rp",
        "rt",
        "ruby",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "td",
        "th",
        "time",
        "tr",
        "tt",
        "u",
        "ul",
        "var",
    ]
)

# HTML tags whose body is not prose at all: markup, data or a generated
# listing, dropped whole the way <math> is.
_OPAQUE_TAGS = frozenset(
    [
        "categorytree",
        "gallery",
        "graph",
        "hiero",
        "imagemap",
        "indicator",
        "mapframe",
        "maplink",
        "pre",
        "score",
        "source",
        "syntaxhighlight",
        "templatedata",
        "timeline",
    ]
)

# Void tags, which have no body to close: "<br>" is written both bare and
# self-closing, and neither form should reach the text.
_VOID_TAGS = frozenset(["br", "hr", "wbr"])


def _tag_name(block: str) -> str:
    """The element name of an HTML tag token, lowercased.

    ``"<ref name=x />"`` gives ``"ref"``, ``"</small>"`` gives ``"small"``,
    and a token that is not a tag gives ``""``.
    """
    if not block.startswith("<") or block.startswith("<!"):
        return ""
    name = block[1:].lstrip("/")
    end = 0
    while end < len(name) and (name[end].isalnum() or name[end] == "-"):
        end += 1
    return name[:end].lower()


# A token is either a structural marker (a bare string) or a parsed block.
Token = str
Node = Union["ParseBlock", Token]


class ParseBlock:
    """One node of the parsed wikitext tree.

    A block is *open* while the tokenizer is still feeding it children and
    closes when its terminator arrives.  Blocks nest, which is the whole point
    of parsing rather than pattern-matching: an open child claims incoming
    tokens until it closes, so an inner ``}}`` closes the inner template.
    """

    def __init__(self, sub_blocks: Optional[List[Node]] = None) -> None:
        self.sub_blocks: List[Node] = sub_blocks if sub_blocks is not None else []
        self.is_open = False

    def add_block(self, block: Node) -> None:
        """Append a token, handing it to the innermost open child first."""
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return

        if block == "&nbsp;":
            self.sub_blocks.append(TextBlock(" "))
        elif isinstance(block, ParseBlock):
            self.sub_blocks.append(block)
        elif block.startswith("</"):
            # A closing tag that reaches here has no open block to close: the
            # block it belonged to was force-closed early by the "\n\n" guard
            # below.  Dropping it is the point -- matching on the tag name
            # alone would open a *new* block, which then swallows the rest of
            # the article.  A taxobox holding an <imagemap> with a blank line
            # in it does exactly that, and cost "Animal", "Bird" and "Mammal"
            # their entire text.
            pass
        elif block.startswith("<!--"):
            self.sub_blocks.append(CommentBlock())
        elif _tag_name(block) == "ref":
            self.sub_blocks.append(ReferenceBlock(block))
        elif _tag_name(block) in ("math", "chem"):
            self.sub_blocks.append(MathBlock(block))
        elif _tag_name(block) == "nowiki":
            self.sub_blocks.append(NowikiBlock(block))
        elif _tag_name(block) in _OPAQUE_TAGS:
            self.sub_blocks.append(OpaqueTagBlock(block))
        elif _tag_name(block) in _VOID_TAGS:
            # A line break separates the words either side of it, so it must
            # not join them into one token: "one<br>two" is two words.
            self.sub_blocks.append(TextBlock(" "))
        elif _tag_name(block) in _PROSE_TAGS:
            # The tag is apparatus; the text it wraps (if any) is prose and is
            # collected by this block's other children, as an emphasis marker's
            # text is.
            pass
        elif block.startswith("<"):
            # An unrecognized tag is still markup, not a word.
            pass
        elif block == "{|":
            self.sub_blocks.append(TableBlock())
            self.sub_blocks[-1].is_open = True  # type: ignore[union-attr]
        elif block == "[[":
            self.sub_blocks.append(LinkBlock())
            self.sub_blocks[-1].is_open = True  # type: ignore[union-attr]
        elif block == "[":
            # A single bracket opens an external link only when a URL follows.
            # In prose "[" is ordinary punctuation -- "[sic]", "[citation
            # needed]", "[1]" -- so the block decides from its first child
            # whether it is a link at all, and renders itself as plain text
            # when it is not.
            self.sub_blocks.append(ExternalLinkBlock())
            self.sub_blocks[-1].is_open = True  # type: ignore[union-attr]
        elif block == "{{":
            self.sub_blocks.append(TemplateBlock())
            self.sub_blocks[-1].is_open = True  # type: ignore[union-attr]
        elif block in ("'''", "''", "'''''"):
            # Emphasis markers wrap text without nesting a block around it;
            # dropping the marker keeps the words it emphasized.
            pass
        elif block.startswith("=="):
            self.sub_blocks.append(HeadingBlock(block))
        else:
            self.sub_blocks.append(TextBlock(block))

    def to_text(self) -> str:
        """Render this block and its children as plain text."""
        return "".join(_node_text(child) for child in self.sub_blocks)


def _node_text(node: Node) -> str:
    """Text contributed by one child node."""
    if isinstance(node, ParseBlock):
        return node.to_text()
    return node


def _node_str(node: Node) -> str:
    """Raw string of a node, for inspecting a block's own markup."""
    if isinstance(node, TextBlock):
        return node.text
    if isinstance(node, ParseBlock):
        return node.to_text()
    return node


class DocumentBlock(ParseBlock):
    """The root of a parsed article."""


class TextBlock(ParseBlock):
    """A run of literal text."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def __eq__(self, other: object) -> bool:
        # Compares equal to its own source string, so a caller scanning
        # children for a separator ("|") finds it whether the tokenizer's
        # token is still a bare string or has become a block.
        if isinstance(other, str):
            return self.text == other
        if isinstance(other, TextBlock):
            return self.text == other.text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)

    def to_text(self) -> str:
        return self.text


class HeadingBlock(ParseBlock):
    """A section heading, which contributes no text.

    Its level is the number of ``=`` signs, and the matching run of ``=``
    closes it.
    """

    def __init__(self, block: str) -> None:
        super().__init__()
        self.is_open = True
        self.level = len(block)

    def add_block(self, block: Node) -> None:
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        if block == "=" * self.level:
            self.is_open = False
            return
        super().add_block(block)

    def to_text(self) -> str:
        # A heading is a label rather than a sentence; see the module
        # docstring.  The newline keeps the sections either side of it from
        # running together into one sentence.
        return "\n"


class LinkBlock(ParseBlock):
    """A ``[[wikilink]]``, contributing its display text."""

    def __init__(self) -> None:
        super().__init__()
        self.malformed = False

    def add_block(self, block: Node) -> None:
        if block == "\n\n":
            # Malformed: an unclosed link cannot span a paragraph break, and
            # leaving it open would swallow the rest of the article.
            self.is_open = False
            self.malformed = True
            return
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        if block == "]]":
            self.is_open = False
            return
        super().add_block(block)

    def to_text(self) -> str:
        if not self.sub_blocks:
            return ""
        head = _node_str(self.sub_blocks[0])
        if head.startswith(_MEDIA_PREFIXES):
            return ""
        # "[[target|display text]]" shows the text after the last pipe;
        # "[[target]]" shows the target itself.
        pipe_index = -1
        for index, child in enumerate(self.sub_blocks):
            if child == "|":
                pipe_index = index
        if pipe_index < 0:
            return "".join(_node_text(child) for child in self.sub_blocks)
        return "".join(_node_text(child) for child in self.sub_blocks[pipe_index + 1 :])


class ExternalLinkBlock(ParseBlock):
    """A ``[url text]`` external link, contributing no text.

    The URL is not prose, and neither is the label beside it: an external link
    is citation apparatus, so its text is "BBC News", "Archived from the
    original" or "Official website" rather than a sentence.  Dropping the whole
    construct is what :class:`ReferenceBlock` does with a ``<ref>``, and for the
    same reason -- the ``<ref>``-wrapped citations were already dropped, while
    these were not, which is how "www", "com", "org" and "html" reached the
    frequency lists.  The word tokenizer splits a bare URL on its punctuation,
    so ``https://www.bbc.co.uk/news`` was counted as six English words.

    Only a bracket that actually opens a link is treated as one: ``[`` is
    ordinary punctuation in prose, so :class:`DocumentBlock` opens this block
    only when a URL scheme follows the bracket.
    """

    def add_block(self, block: Node) -> None:
        if block == "\n\n":
            # Malformed: an unclosed link cannot span a paragraph break, and
            # leaving it open would swallow the rest of the article.  Same
            # guard as LinkBlock's.
            self.is_open = False
            return
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        if block == "]":
            self.is_open = False
            return
        super().add_block(block)

    def _is_link(self) -> bool:
        """Whether a URL scheme follows the bracket."""
        if not self.sub_blocks:
            return False
        return _node_str(self.sub_blocks[0]).startswith(_URL_PREFIXES)

    def to_text(self) -> str:
        if self._is_link():
            return ""
        # Not a link: "[sic]" and "[1]" are prose, so the bracket and the text
        # inside it are kept as they were written.
        inner = "".join(_node_text(child) for child in self.sub_blocks)
        return f"[{inner}]" if not self.is_open else f"[{inner}"


class TemplateBlock(ParseBlock):
    """A ``{{template}}``, contributing text only for :data:`RAW_TEMPLATES`."""

    def add_block(self, block: Node) -> None:
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        if block == "}}":
            self.is_open = False
            return
        super().add_block(block)

    def kind(self) -> str:
        """The template's name, lowercased (the part before the first pipe)."""
        joined = "".join(_node_str(child) for child in self.sub_blocks)
        return joined.split("|")[0].strip().lower()

    def _arguments(self) -> List[str]:
        """The pipe-separated arguments, positional ones only."""
        parts: List[str] = [""]
        for child in self.sub_blocks:
            if child == "|":
                parts.append("")
            else:
                parts[-1] += _node_text(child)
        return parts

    def to_text(self) -> str:
        kind = self.kind()
        if kind not in RAW_TEMPLATES:
            return ""
        arguments = [part.strip() for part in self._arguments()[1:]]
        # Named parameters carry markup settings, not prose.
        arguments = [part for part in arguments if part and "=" not in part]
        if not arguments:
            return ""
        if kind == "lang":
            # "{{lang|fr|coup d'etat}}": the first argument is a language code.
            return arguments[-1]
        if kind == "nihongo":
            # "{{nihongo|Tokyo|...}}": the English reading comes first.
            return arguments[0]
        return " ".join(arguments)


class ReferenceBlock(ParseBlock):
    """A ``<ref>`` citation, contributing no text."""

    def __init__(self, block: str) -> None:
        super().__init__()
        # A self-closing "<ref name=x />" has no body to consume.
        self.is_open = not block.endswith("/>")

    def add_block(self, block: Node) -> None:
        if block == "</ref>":
            self.is_open = False
            return
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        super().add_block(block)

    def to_text(self) -> str:
        return ""


class MathBlock(ParseBlock):
    """A ``<math>`` formula, contributing no text.

    The body is LaTeX, not prose.  Left in, its control sequences are counted
    as English words: ``frac`` was the wiki_math corpus's 4068-count entry,
    with ``mathbf``, ``cdot``, ``sqrt``, ``infty`` and the spelled-out Greek
    letters close behind.  Those are notation, and a learner meets none of them
    as vocabulary.

    ``sin``/``cos``/``tan`` come from here too.  They are real abbreviations
    rather than markup, but a corpus counting them is measuring formulas, not
    the English around them.

    Also covers ``<chem>``, whose body is chemical markup with the same
    problem.
    """

    def __init__(self, block: str) -> None:
        super().__init__()
        # A self-closing "<math />" has no body to consume.
        self.is_open = not block.endswith("/>")

    def add_block(self, block: Node) -> None:
        if isinstance(block, str) and block in ("</math>", "</chem>"):
            self.is_open = False
            return
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        super().add_block(block)

    def to_text(self) -> str:
        return ""


class OpaqueTagBlock(ParseBlock):
    """An HTML tag in :data:`_OPAQUE_TAGS`, contributing no text.

    Its body is markup or generated apparatus rather than prose -- a
    ``<gallery>`` is a list of filenames, a ``<syntaxhighlight>`` is source
    code -- so it is dropped whole, as :class:`MathBlock` drops a formula.
    """

    def __init__(self, block: str) -> None:
        super().__init__()
        self.name = _tag_name(block)
        # A self-closing "<gallery />" has no body to consume.
        self.is_open = not block.endswith("/>")

    def add_block(self, block: Node) -> None:
        if isinstance(block, str) and _tag_name(block) == self.name and block.startswith("</"):
            self.is_open = False
            return
        if block == "\n\n":
            # Malformed: an unclosed tag must not swallow the rest of the
            # article.  These blocks are long and hand-edited, so a missing
            # close is likelier here than on a one-line <math>, and the cost is
            # the whole article rather than one construct.  Same guard as
            # LinkBlock's.
            self.is_open = False
            return
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        super().add_block(block)

    def to_text(self) -> str:
        return ""


class NowikiBlock(ParseBlock):
    """A ``<nowiki>`` span, whose body is literal text rather than markup.

    The body is kept -- it is prose the author wanted shown verbatim -- but
    without letting the wikitext constructs inside it open blocks, which is the
    whole point of the tag.
    """

    def __init__(self, block: str) -> None:
        super().__init__()
        self.is_open = not block.endswith("/>")

    def add_block(self, block: Node) -> None:
        if isinstance(block, str) and _tag_name(block) == "nowiki" and block.startswith("</"):
            self.is_open = False
            return
        # Every token is literal, so no child block is opened.
        self.sub_blocks.append(TextBlock(_node_str(block)))

    def to_text(self) -> str:
        return "".join(_node_text(child) for child in self.sub_blocks)


class TableBlock(ParseBlock):
    """A ``{| ... |}`` table, contributing no text."""

    def add_block(self, block: Node) -> None:
        if self.sub_blocks:
            last = self.sub_blocks[-1]
            if isinstance(last, ParseBlock) and last.is_open:
                last.add_block(block)
                return
        if block == "|}":
            self.is_open = False
            return
        super().add_block(block)

    def to_text(self) -> str:
        return ""


class CommentBlock(ParseBlock):
    """An HTML comment, contributing no text."""

    def to_text(self) -> str:
        return ""


class WikiTokenizer:
    """Split wikitext into structural markers and runs of text.

    Character-level rather than regex-based, because the markers are ambiguous
    in a way patterns handle badly: ``|`` separates template arguments but also
    starts a table cell, ``{`` opens a template only when doubled, and ``'``
    is both an apostrophe and an emphasis marker depending on how many are in a
    row.  Deciding that per character, with the table state known, is what
    makes the result reliable.

    Attributes:
        page_name: Article title, used in error messages.
        tokens: Structural markers and text runs, in order.
        unhandled: Characters that fell through to single-character tokens,
            kept for diagnosing a construct this does not yet know about.
    """

    def __init__(self, page_name: str = "") -> None:
        self.page_name = page_name
        self.current_token = ""
        self.tokens: List[str] = []
        self.unhandled: Set[str] = set()

    def clear_token(self) -> None:
        """Emit the token under construction, if any."""
        if self.current_token:
            self.tokens.append(self.current_token)
        self.current_token = ""

    def tokenize(self, text: str) -> DocumentBlock:
        """Tokenize ``text`` and assemble it into a block tree."""
        in_text = False
        in_tag = False
        in_table = False
        in_comment = False

        for char in text:
            if in_table and char in "|-}":
                # "|-" (row break) and "|}" (table end) must not be split into
                # a pipe plus a character, or the table would never close.
                if self.current_token == "|" and char == "-":
                    self.current_token += char
                    self.clear_token()
                    continue
                if self.current_token == "|" and char == "}":
                    self.current_token += char
                    self.clear_token()
                    in_table = False
                    continue
                if char == "|":
                    self.clear_token()
                    self.current_token += char
                    continue
            if in_table and self.current_token == "|":
                self.clear_token()

            if in_tag:
                if in_comment:
                    if char == ">" and self.current_token.endswith("--"):
                        self.current_token += char
                        self.clear_token()
                        in_tag = False
                        in_comment = False
                    else:
                        self.current_token += char
                    continue
                if self.current_token == "<!--":
                    in_comment = True
                    self.current_token += char
                    continue
                self.current_token += char
                if char == ">":
                    in_tag = False
                    self.clear_token()
                continue

            if char.isalpha() or char.isnumeric() or char in ("/", ".", ",", ":", "-", "(", ")"):
                if not in_text:
                    self.clear_token()
                    in_text = True
                self.current_token += char
            elif char == ";":
                # Terminates an entity such as "&nbsp;"; otherwise ordinary
                # punctuation.
                if in_text and self.current_token.startswith("&"):
                    self.current_token += char
                    self.clear_token()
                else:
                    self.clear_token()
                    self.tokens.append(";")
                in_text = False
            elif char == "&":
                self.clear_token()
                self.current_token += char
                in_text = True
            elif char == "<":
                self.clear_token()
                in_text = False
                in_tag = True
                self.current_token += char
            elif char == "|":
                if self.current_token == "{":
                    # "{|" opens a table.
                    self.current_token += char
                    self.clear_token()
                    in_table = True
                else:
                    self.clear_token()
                    self.tokens.append("|")
                    in_text = False
            elif char in ("]", "}"):
                # Group at most two, so "}}}" closes a template and leaves a
                # brace rather than becoming one unknown token.
                if self.current_token == char:
                    self.current_token += char
                else:
                    self.clear_token()
                    self.current_token += char
                    in_text = False
            elif char in ("[", "{", "=", "\n", "'"):
                # Group any run: "=====" is one heading marker and "'''''" is
                # one emphasis marker.
                if self.current_token and self.current_token[0] == char:
                    self.current_token += char
                else:
                    self.clear_token()
                    self.current_token += char
                    in_text = False
            elif char == " ":
                self.clear_token()
                self.tokens.append(char)
                in_text = False
            else:
                self.unhandled.add(char)
                self.clear_token()
                self.tokens.append(char)
                in_text = False

        self.clear_token()

        document = DocumentBlock()
        for token in self.tokens:
            document.add_block(token)
        return document


# Redirect stubs carry a single link and no prose.
_REDIRECT_PREFIX = "#REDIRECT"


def is_redirect(wikitext: str) -> bool:
    """Whether ``wikitext`` is a redirect stub rather than an article."""
    return wikitext.lstrip()[: len(_REDIRECT_PREFIX)].upper() == _REDIRECT_PREFIX


def parse(wikitext: str, page_name: str = "") -> DocumentBlock:
    """Parse ``wikitext`` into a block tree."""
    return WikiTokenizer(page_name).tokenize(wikitext)


# A bare URL written in running prose, which no bracket construct covers.
# Matched on the rendered text rather than during tokenization because the
# tokenizer splits a URL across several tokens ("https", "://", "www.bbc.co.uk")
# and rejoining them there would mean re-parsing.
_BARE_URL_RE = re.compile(r"(?:https?://|ftp://|www\.)\S+", re.IGNORECASE)


def _strip_bare_urls(text: str) -> str:
    """Drop URLs written directly into prose.

    The word tokenizer splits on punctuation, so a surviving
    ``https://www.bbc.co.uk/news`` is counted as "https", "www", "bbc", "co",
    "uk" and "news" -- six entries in an English frequency list, none of them
    words.
    """
    return _BARE_URL_RE.sub(" ", text)


def _collapse_whitespace(text: str) -> str:
    """Normalize the whitespace left behind by removed constructs."""
    lines = [line.strip() for line in text.splitlines()]
    paragraphs: List[str] = []
    current: List[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def wikitext_to_plain_text(wikitext: str, page_name: str = "") -> str:
    """Extract an article's running prose from its wikitext.

    Templates, tables, references, headings and media links are dropped; link
    display text is kept.  See the module docstring for why each one.

    Args:
        wikitext: The article source, as stored in the dump.
        page_name: Article title, used in error messages.

    Returns:
        The article's prose, with paragraphs separated by blank lines.  A
        redirect stub yields the empty string.
    """
    if is_redirect(wikitext):
        return ""
    return _collapse_whitespace(_strip_bare_urls(parse(wikitext, page_name).to_text()))
