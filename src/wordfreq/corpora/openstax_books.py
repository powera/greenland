"""The OpenStax textbooks behind the three OpenStax corpora, pinned by commit.

OpenStax publishes each book's CNXML source as a GitHub repository
(``openstax/osbooks-<name>``), one repository per book or per bundle of
closely related books.  On 2026-04-23 it relicensed almost the whole catalogue
from CC BY 4.0 to CC BY-NC-SA 4.0, and this project does not use NC-SA text.
A Creative Commons license cannot be withdrawn from copies already released
under it, so every book here is pinned to the last commit whose collection
file still declares CC BY 4.0: the parent of the relicensing commit.
``download_openstax.py`` checks the declared license at the pin before it
checks the text out.

Left out, and why:

* Organic Chemistry, Principles of Accounting (both volumes) and Business Law I
  Essentials were CC BY-NC-SA from their first commit, so no CC BY version
  exists.
* Introduction to Philosophy and Principles of Finance are pinned at their
  first editions: the second editions were published on 2026-04-28 under
  NC-SA only.
* Principles of Management and Organizational Behavior share a repository, so
  share a pin: Management's, 2026-04-14, when both were still CC BY.  That
  loses Organizational Behavior's edits of the following nine days.
* Duplicate editions: Biology for AP Courses and Concepts of Biology share most
  of Biology 2e's text, Chemistry: Atoms First is Chemistry 2e reordered, and
  Principles of Micro- and Macroeconomics are copied from Principles of
  Economics.  Counting both would count the same sentences twice.
* University Physics: College Physics covers the same ground in prose rather
  than calculus.
* Mathematics and nursing: out of scope (see ``README.md``).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

#: The license every pinned book must declare at its pin.
REQUIRED_LICENSE_URL = "creativecommons.org/licenses/by/4.0"


@dataclass(frozen=True)
class OpenStaxBook:
    """One book: where its source lives and which commit to read.

    Attributes:
        slug: Short stable name, used as the prefix of every chapter slug.
        title: The book's title as its collection file gives it.
        repo: GitHub repository name under ``openstax/``.
        collection: Collection file name in the repository's ``collections/``.
        commit: The pinned commit: the last one declaring CC BY 4.0.
        pinned_on: That commit's date, for review.
    """

    slug: str
    title: str
    repo: str
    collection: str
    commit: str
    pinned_on: str


OPENSTAX_SCIENCE: Tuple[OpenStaxBook, ...] = (
    OpenStaxBook(
        slug="biology",
        title="Biology 2e",
        repo="osbooks-biology-bundle",
        collection="biology-2e.collection.xml",
        commit="ce66bceda29ef1ce4d4a178e072af4b735e70b84",
        pinned_on="2026-04-21",
    ),
    OpenStaxBook(
        slug="microbiology",
        title="Microbiology",
        repo="osbooks-microbiology",
        collection="microbiology.collection.xml",
        commit="f1d8d4e9941417f25610a239045c35488d56cf22",
        pinned_on="2026-03-19",
    ),
    OpenStaxBook(
        slug="anatomy",
        title="Anatomy and Physiology 2e",
        repo="osbooks-anatomy-physiology",
        collection="anatomy-and-physiology-2e.collection.xml",
        commit="7d142c477b7324d24c05ca65d850fafef561e55d",
        pinned_on="2026-04-20",
    ),
    OpenStaxBook(
        slug="neuroscience",
        title="Introduction to Behavioral Neuroscience",
        repo="osbooks-neuroscience",
        collection="introduction-behavioral-neuroscience.collection.xml",
        commit="411de04445caf4a8ce1a6da21c5c4b5dfe5a29d9",
        pinned_on="2024-11-11",
    ),
    OpenStaxBook(
        slug="chemistry",
        title="Chemistry 2e",
        repo="osbooks-chemistry-bundle",
        collection="chemistry-2e.collection.xml",
        commit="7d41ed008e9b83a6690c09c26a16f63f96046ec0",
        pinned_on="2026-04-15",
    ),
    OpenStaxBook(
        slug="physics",
        title="College Physics 2e",
        repo="osbooks-college-physics-bundle",
        collection="college-physics-2e.collection.xml",
        commit="379f0809c389e1abc0f4af167bcb00ce3e89745d",
        pinned_on="2026-04-23",
    ),
    OpenStaxBook(
        slug="astronomy",
        title="Astronomy 2e",
        repo="osbooks-astronomy",
        collection="astronomy-2e.collection.xml",
        commit="4aedbad89cb6b91004a2fd0cba74c813d78bbd1d",
        pinned_on="2026-03-12",
    ),
    OpenStaxBook(
        slug="python",
        title="Introduction to Python Programming",
        repo="osbooks-introduction-python-programming",
        collection="introduction-python-programming.collection.xml",
        commit="a3f0ad346e0d77f8ed94440d7c39059d0c4d927c",
        pinned_on="2026-04-07",
    ),
    OpenStaxBook(
        slug="data_science",
        title="Principles of Data Science",
        repo="osbooks-principles-data-science",
        collection="principles-data-science.collection.xml",
        commit="e9fbc64ccb92f58f1cefe526e49a69854a681805",
        pinned_on="2024-11-15",
    ),
    OpenStaxBook(
        slug="information_systems",
        title="Foundations of Information Systems",
        repo="osbooks-foundations-information-systems",
        collection="foundations-information-systems.collection.xml",
        commit="2959814de655db6018ed461aaa65b53616b94af2",
        pinned_on="2025-02-05",
    ),
)

OPENSTAX_SOCIETY: Tuple[OpenStaxBook, ...] = (
    OpenStaxBook(
        slug="psychology",
        title="Psychology 2e",
        repo="osbooks-psychology",
        collection="psychology-2e.collection.xml",
        commit="e91efc4674c71be3c9b13b16766078dfafa06ebb",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="lifespan",
        title="Lifespan Development",
        repo="osbooks-lifespan-development",
        collection="lifespan-development.collection.xml",
        commit="26d84bf43131d2458732295d473d8519c550ade1",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="sociology",
        title="Introduction to Sociology 3e",
        repo="osbooks-introduction-sociology",
        collection="introduction-sociology-3e.collection.xml",
        commit="cb424bc47ff1be02df7cff71d7e8d9ead113ba3c",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="anthropology",
        title="Introduction to Anthropology",
        repo="osbooks-introduction-anthropology",
        collection="introduction-anthropology.collection.xml",
        commit="e1ed1ad3654ea091087859681a558cf603283e62",
        pinned_on="2026-04-07",
    ),
    OpenStaxBook(
        slug="political_science",
        title="Introduction to Political Science",
        repo="osbooks-introduction-political-science",
        collection="introduction-political-science.collection.xml",
        commit="da3ba0d26f42caded8c4df531ff0703d42813465",
        pinned_on="2026-03-20",
    ),
    OpenStaxBook(
        slug="american_government",
        title="American Government 4e",
        repo="osbooks-american-government",
        collection="american-government-4e.collection.xml",
        commit="4c379bad6150a1f831a3281240180ed81aeeb980",
        pinned_on="2026-04-08",
    ),
    OpenStaxBook(
        slug="economics",
        title="Principles of Economics 3e",
        repo="osbooks-principles-economics-bundle",
        collection="principles-economics-3e.collection.xml",
        commit="1a5128dd299708e9a59eb38941b1ff1410bc1e63",
        pinned_on="2026-03-20",
    ),
    OpenStaxBook(
        slug="us_history",
        title="U.S. History",
        repo="osbooks-us-history",
        collection="us-history.collection.xml",
        commit="ec99b9ad7e897c7f38339f0a32cde8d6f193d741",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="world_history_1",
        title="World History Volume 1, to 1500",
        repo="osbooks-world-history",
        collection="world-history-volume-1.collection.xml",
        commit="b2ddac6d5ab41847257c1484ee9271576d1a053e",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="world_history_2",
        title="World History Volume 2, from 1400",
        repo="osbooks-world-history",
        collection="world-history-volume-2.collection.xml",
        commit="b2ddac6d5ab41847257c1484ee9271576d1a053e",
        pinned_on="2026-03-23",
    ),
    OpenStaxBook(
        slug="philosophy",
        title="Introduction to Philosophy",
        repo="osbooks-introduction-philosophy",
        collection="introduction-philosophy.collection.xml",
        commit="11e401a3125cd3a951fa933abf2776d01a904597",
        pinned_on="2026-04-07",
    ),
)

OPENSTAX_BUSINESS: Tuple[OpenStaxBook, ...] = (
    OpenStaxBook(
        slug="business",
        title="Introduction to Business 2e",
        repo="osbooks-introduction-business",
        collection="introduction-business-2e.collection.xml",
        commit="f99a5bb2eeec22a6fb042f8d95435d5b9e5564da",
        pinned_on="2026-04-03",
    ),
    OpenStaxBook(
        slug="management",
        title="Principles of Management",
        repo="osbooks-principles-of-management-bundle",
        collection="principles-management.collection.xml",
        commit="7ee7a847ce624b6e101f58578d4a07c3a6998577",
        pinned_on="2026-04-14",
    ),
    OpenStaxBook(
        slug="organizational_behavior",
        title="Organizational Behavior",
        repo="osbooks-principles-of-management-bundle",
        collection="organizational-behavior.collection.xml",
        commit="7ee7a847ce624b6e101f58578d4a07c3a6998577",
        pinned_on="2026-04-14",
    ),
    OpenStaxBook(
        slug="marketing",
        title="Principles of Marketing",
        repo="osbooks-principles-marketing",
        collection="principles-marketing.collection.xml",
        commit="2720b927e36431f7c24759dc06838ea19c1f3770",
        pinned_on="2026-04-07",
    ),
    OpenStaxBook(
        slug="entrepreneurship",
        title="Entrepreneurship",
        repo="osbooks-entrepreneurship",
        collection="entrepreneurship.collection.xml",
        commit="4fd385dc7b75e5e7cbdccb59c4149b4af220a88b",
        pinned_on="2026-04-14",
    ),
    OpenStaxBook(
        slug="business_ethics",
        title="Business Ethics",
        repo="osbooks-business-ethics",
        collection="business-ethics.collection.xml",
        commit="cbf8eb4fbbabb2f8e01890e2848c82c1182c7ba5",
        pinned_on="2026-04-14",
    ),
    OpenStaxBook(
        slug="finance",
        title="Principles of Finance",
        repo="osbooks-principles-finance",
        collection="principles-finance.collection.xml",
        commit="c802474325f10146c2ba1ca9af727b7940c19772",
        pinned_on="2026-04-08",
    ),
    OpenStaxBook(
        slug="intellectual_property",
        title="Introduction to Intellectual Property",
        repo="osbooks-introduction-intellectual-property",
        collection="introduction-intellectual-property.collection.xml",
        commit="6dad5479f5a7974df9a2dcb01f4ce9a970658029",
        pinned_on="2026-04-23",
    ),
)

OPENSTAX_CORPORA: Dict[str, Tuple[OpenStaxBook, ...]] = {
    "openstax_science": OPENSTAX_SCIENCE,
    "openstax_society": OPENSTAX_SOCIETY,
    "openstax_business": OPENSTAX_BUSINESS,
}


def get_books(corpus: str) -> Tuple[OpenStaxBook, ...]:
    """The books of one corpus, or every book (once each) for ``"all"``."""
    if corpus == "all":
        return tuple(book for books in OPENSTAX_CORPORA.values() for book in books)
    try:
        return OPENSTAX_CORPORA[corpus]
    except KeyError:
        raise ValueError(
            f"unknown OpenStax corpus {corpus!r}; expected one of {sorted(OPENSTAX_CORPORA)}"
        ) from None


def repo_pins(books: Tuple[OpenStaxBook, ...]) -> Dict[str, str]:
    """``{repo: commit}`` for a set of books.

    A repository is checked out at one commit, so two books from the same
    bundle must share their pin.

    Raises:
        ValueError: If two books in one repository name different commits.
    """
    pins: Dict[str, str] = {}
    for book in books:
        existing = pins.setdefault(book.repo, book.commit)
        if existing != book.commit:
            raise ValueError(
                f"{book.repo} is pinned at both {existing[:10]} and {book.commit[:10]}"
            )
    return pins


def corpus_choices() -> List[str]:
    """CLI choices: each corpus name, then ``"all"``."""
    return [*OPENSTAX_CORPORA, "all"]
