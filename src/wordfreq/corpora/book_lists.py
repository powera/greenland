"""Project Gutenberg book lists for the generated word-frequency corpora.

Every entry has been checked against Gutenberg metadata: ``title`` and
``author`` are the catalogue values for ``gutenberg_id``.  ``year`` is the
work's first publication (not the Gutenberg posting date), which is what places
a book in the 19th- or 20th-century list; for the religious corpus, whose works
long predate any of these lists, it is the year of the English translation.

Selection principles, since the point of these corpora is general vocabulary
frequency rather than a literary canon:

* At most two works per author, so no one writer's habits of vocabulary set a
  word's rank.
* Breadth over prominence.  A word's rank should come from many authors, so
  each list mixes British, American and translated European writing, several
  genres, and some non-fiction - no single famous book decides a word's rank.
* No work appears twice.  A complete posting and its volume splits are never
  both included; where only volume splits exist, either one volume stands for
  the work or the work is left out.
* Nothing so short that it cannot carry its own weight; see
  ``frequency_build.DEFAULT_FULL_WEIGHT_TOKENS`` for how length is handled.

Books with heavy topic-specific vocabulary (whaling, seafaring, war) are fine
here: :mod:`wordfreq.corpora.frequency_build` averages each word's *rate*
across books rather than pooling raw counts, so one book cannot push its own
jargon up the list.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from wordfreq.corpora.gutenberg_text import slugify_title


@dataclass(frozen=True)
class GutenbergBook:
    """One book in a corpus book list.

    Attributes:
        gutenberg_id: Project Gutenberg ebook number.
        title: Catalogue title, also used to build the corpus JSON key.
        author: Catalogue author (``""`` for anonymous/compiled works).
        year: For the century corpora, the year the work was first published,
            which is what places it in the 19th- or 20th-century list.  For
            ``religious_translated`` the works themselves are ancient, so this
            is the year of the English translation printed in this edition -
            the translation is what the corpus actually measures.
        note: Optional remark: source language, translator, or why the book is
            in the list.
    """

    gutenberg_id: int
    title: str
    author: str
    year: Optional[int] = None
    note: str = ""

    @property
    def slug(self) -> str:
        """Key used for this book in the corpus JSON (``<id>_<Title>``)."""
        return slugify_title(self.gutenberg_id, self.title)

    @property
    def id_verified(self) -> bool:
        """Whether this ID has been checked against Gutenberg's catalogue."""
        return self.gutenberg_id not in UNVERIFIED_IDS


@dataclass(frozen=True)
class BookList:
    """A named corpus and the books it is built from.

    Attributes:
        corpus_name: Corpus name, matching ``wordfreq.frequency.corpus``.
        description: Human-readable description of the corpus.
        max_words: Default number of words to keep in the generated JSON.
        books: The books making up the corpus.
        always_vocabulary: Words this corpus keeps as ordinary vocabulary even
            though they are almost always capitalized, and so would otherwise
            be classified as proper nouns and dropped.
    """

    corpus_name: str
    description: str
    max_words: int
    books: Tuple[GutenbergBook, ...]
    always_vocabulary: Tuple[str, ...] = ()

    @property
    def gutenberg_ids(self) -> List[int]:
        """Gutenberg IDs of every book in the list."""
        return [book.gutenberg_id for book in self.books]


# --- 19th century ------------------------------------------------------------

NINETEENTH_CENTURY_BOOKS: Tuple[GutenbergBook, ...] = (
    # British novels
    GutenbergBook(1342, "Pride and Prejudice", "Austen, Jane", 1813),
    GutenbergBook(158, "Emma", "Austen, Jane", 1815),
    GutenbergBook(1260, "Jane Eyre: An Autobiography", "Brontë, Charlotte", 1847),
    GutenbergBook(9182, "Villette", "Brontë, Charlotte", 1853),
    GutenbergBook(768, "Wuthering Heights", "Brontë, Emily", 1847),
    GutenbergBook(145, "Middlemarch", "Eliot, George", 1872),
    GutenbergBook(550, "Silas Marner", "Eliot, George", 1861),
    GutenbergBook(1400, "Great Expectations", "Dickens, Charles", 1861),
    GutenbergBook(766, "David Copperfield", "Dickens, Charles", 1850),
    GutenbergBook(394, "Cranford", "Gaskell, Elizabeth Cleghorn", 1853),
    GutenbergBook(110, "Tess of the d'Urbervilles: A Pure Woman", "Hardy, Thomas", 1891),
    GutenbergBook(153, "Jude the Obscure", "Hardy, Thomas", 1895),
    GutenbergBook(155, "The Moonstone", "Collins, Wilkie", 1868),
    GutenbergBook(583, "The Woman in White", "Collins, Wilkie", 1859),
    GutenbergBook(174, "The Picture of Dorian Gray", "Wilde, Oscar", 1890),
    GutenbergBook(2166, "King Solomon's Mines", "Haggard, H. Rider", 1885),
    # Adventure, gothic, early science fiction
    GutenbergBook(
        84, "Frankenstein; Or, The Modern Prometheus", "Shelley, Mary Wollstonecraft", 1818
    ),
    GutenbergBook(345, "Dracula", "Stoker, Bram", 1897),
    GutenbergBook(
        43, "The Strange Case of Dr. Jekyll and Mr. Hyde", "Stevenson, Robert Louis", 1886
    ),
    GutenbergBook(120, "Treasure Island", "Stevenson, Robert Louis", 1883),
    GutenbergBook(35, "The Time Machine", "Wells, H. G.", 1895),
    GutenbergBook(36, "The War of the Worlds", "Wells, H. G.", 1898),
    GutenbergBook(1661, "The Adventures of Sherlock Holmes", "Doyle, Arthur Conan", 1892),
    GutenbergBook(244, "A Study in Scarlet", "Doyle, Arthur Conan", 1887),
    GutenbergBook(10007, "Carmilla", "Le Fanu, Joseph Sheridan", 1872),
    # American
    GutenbergBook(76, "Adventures of Huckleberry Finn", "Twain, Mark", 1884),
    GutenbergBook(74, "The Adventures of Tom Sawyer, Complete", "Twain, Mark", 1876),
    GutenbergBook(2701, "Moby Dick; Or, The Whale", "Melville, Herman", 1851),
    GutenbergBook(25344, "The Scarlet Letter", "Hawthorne, Nathaniel", 1850),
    GutenbergBook(203, "Uncle Tom's Cabin", "Stowe, Harriet Beecher", 1852),
    GutenbergBook(514, "Little Women", "Alcott, Louisa May", 1868),
    GutenbergBook(73, "The Red Badge of Courage", "Crane, Stephen", 1895),
    GutenbergBook(160, "The Awakening, and Selected Short Stories", "Chopin, Kate", 1899),
    GutenbergBook(209, "The Turn of the Screw", "James, Henry", 1898),
    GutenbergBook(2147, "The Works of Edgar Allan Poe — Volume 1", "Poe, Edgar Allan", 1845),
    # Translated from European languages
    GutenbergBook(2554, "Crime and Punishment", "Dostoyevsky, Fyodor", 1866),
    GutenbergBook(28054, "The Brothers Karamazov", "Dostoyevsky, Fyodor", 1880),
    GutenbergBook(1399, "Anna Karenina", "Tolstoy, Leo", 1878),
    GutenbergBook(2600, "War and Peace", "Tolstoy, Leo", 1869),
    GutenbergBook(1184, "The Count of Monte Cristo", "Dumas, Alexandre", 1845),
    GutenbergBook(1257, "The Three Musketeers", "Dumas, Alexandre", 1844),
    GutenbergBook(135, "Les Misérables", "Hugo, Victor", 1862),
    GutenbergBook(2413, "Madame Bovary", "Flaubert, Gustave", 1856),
    GutenbergBook(164, "Twenty Thousand Leagues under the Sea", "Verne, Jules", 1870),
    GutenbergBook(103, "Around the World in Eighty Days", "Verne, Jules", 1873),
    GutenbergBook(500, "The Adventures of Pinocchio", "Collodi, Carlo", 1883),
    # Children's books and fairy tales
    GutenbergBook(11, "Alice's Adventures in Wonderland", "Carroll, Lewis", 1865),
    GutenbergBook(12, "Through the Looking-Glass", "Carroll, Lewis", 1871),
    GutenbergBook(2591, "Grimms' Fairy Tales", "Grimm, Jacob and Wilhelm", 1812),
    GutenbergBook(271, "Black Beauty: The Autobiography of a Horse", "Sewell, Anna", 1877),
    GutenbergBook(236, "The Jungle Book", "Kipling, Rudyard", 1894),
    # Non-fiction and essays
    GutenbergBook(
        205, "Walden, and On The Duty Of Civil Disobedience", "Thoreau, Henry David", 1854
    ),
    GutenbergBook(61, "The Communist Manifesto", "Marx, Karl; Engels, Friedrich", 1848),
    GutenbergBook(1998, "Thus Spake Zarathustra", "Nietzsche, Friedrich Wilhelm", 1883),
    GutenbergBook(1322, "Leaves of Grass", "Whitman, Walt", 1855),
)

# --- 20th century ------------------------------------------------------------

TWENTIETH_CENTURY_BOOKS: Tuple[GutenbergBook, ...] = (
    # British and Irish novels
    GutenbergBook(2852, "The Hound of the Baskervilles", "Doyle, Arthur Conan", 1902),
    GutenbergBook(139, "The Lost World", "Doyle, Arthur Conan", 1912),
    GutenbergBook(974, "The Secret Agent: A Simple Tale", "Conrad, Joseph", 1907),
    GutenbergBook(5658, "Lord Jim", "Conrad, Joseph", 1900),
    GutenbergBook(2226, "Kim", "Kipling, Rudyard", 1901),
    GutenbergBook(1695, "The Man Who Was Thursday: A Nightmare", "Chesterton, G. K.", 1908),
    GutenbergBook(204, "The Innocence of Father Brown", "Chesterton, G. K.", 1911),
    GutenbergBook(2641, "A Room with a View", "Forster, E. M.", 1908),
    GutenbergBook(2891, "Howards End", "Forster, E. M.", 1910),
    GutenbergBook(217, "Sons and Lovers", "Lawrence, D. H.", 1913),
    GutenbergBook(28948, "The Rainbow", "Lawrence, D. H.", 1915),
    GutenbergBook(351, "Of Human Bondage", "Maugham, W. Somerset", 1915),
    GutenbergBook(222, "The Moon and Sixpence", "Maugham, W. Somerset", 1919),
    GutenbergBook(1245, "Night and Day", "Woolf, Virginia", 1919),
    GutenbergBook(71865, "Mrs. Dalloway", "Woolf, Virginia", 1925),
    GutenbergBook(2814, "Dubliners", "Joyce, James", 1914),
    GutenbergBook(4217, "A Portrait of the Artist as a Young Man", "Joyce, James", 1916),
    GutenbergBook(863, "The Mysterious Affair at Styles", "Christie, Agatha", 1920),
    GutenbergBook(1155, "The Secret Adversary", "Christie, Agatha", 1922),
    GutenbergBook(558, "The Thirty-Nine Steps", "Buchan, John", 1915),
    GutenbergBook(60, "The Scarlet Pimpernel", "Orczy, Emmuska", 1905),
    GutenbergBook(8164, "My Man Jeeves", "Wodehouse, P. G.", 1919),
    GutenbergBook(16389, "The Enchanted April", "Von Arnim, Elizabeth", 1922),
    # American novels
    GutenbergBook(64317, "The Great Gatsby", "Fitzgerald, F. Scott", 1925),
    GutenbergBook(805, "This Side of Paradise", "Fitzgerald, F. Scott", 1920),
    GutenbergBook(67138, "The Sun Also Rises", "Hemingway, Ernest", 1926),
    GutenbergBook(541, "The Age of Innocence", "Wharton, Edith", 1920),
    GutenbergBook(284, "The House of Mirth", "Wharton, Edith", 1905),
    GutenbergBook(543, "Main Street", "Lewis, Sinclair", 1920),
    GutenbergBook(1156, "Babbitt", "Lewis, Sinclair", 1922),
    GutenbergBook(242, "My Ántonia", "Cather, Willa", 1918),
    GutenbergBook(24, "O Pioneers!", "Cather, Willa", 1913),
    GutenbergBook(416, "Winesburg, Ohio", "Anderson, Sherwood", 1919),
    GutenbergBook(233, "Sister Carrie: A Novel", "Dreiser, Theodore", 1900),
    GutenbergBook(140, "The Jungle", "Sinclair, Upton", 1906),
    GutenbergBook(215, "The Call of the Wild", "London, Jack", 1903),
    GutenbergBook(910, "White Fang", "London, Jack", 1906),
    GutenbergBook(11012, "The Autobiography of an Ex-Colored Man", "Johnson, James Weldon", 1912),
    GutenbergBook(32, "Herland", "Gilman, Charlotte Perkins", 1915),
    GutenbergBook(1250, "Anthem", "Rand, Ayn", 1938),
    # Popular and genre fiction
    GutenbergBook(78, "Tarzan of the Apes", "Burroughs, Edgar Rice", 1912),
    GutenbergBook(62, "A Princess of Mars", "Burroughs, Edgar Rice", 1912),
    GutenbergBook(1300, "Riders of the Purple Sage", "Grey, Zane", 1912),
    GutenbergBook(175, "The Phantom of the Opera", "Leroux, Gaston", 1910),
    GutenbergBook(434, "The Circular Staircase", "Rinehart, Mary Roberts", 1908),
    GutenbergBook(1013, "The First Men in the Moon", "Wells, H. G.", 1901),
    # Children's books
    GutenbergBook(55, "The Wonderful Wizard of Oz", "Baum, L. Frank", 1900),
    GutenbergBook(113, "The Secret Garden", "Burnett, Frances Hodgson", 1911),
    GutenbergBook(146, "A Little Princess", "Burnett, Frances Hodgson", 1905),
    GutenbergBook(45, "Anne of Green Gables", "Montgomery, L. M.", 1908),
    GutenbergBook(47, "Anne of Avonlea", "Montgomery, L. M.", 1909),
    GutenbergBook(289, "The Wind in the Willows", "Grahame, Kenneth", 1908),
    GutenbergBook(16, "Peter Pan (Peter and Wendy)", "Barrie, J. M.", 1911),
    GutenbergBook(1874, "The Railway Children", "Nesbit, E.", 1906),
    GutenbergBook(501, "The Story of Doctor Dolittle", "Lofting, Hugh", 1920),
    GutenbergBook(2781, "Just So Stories", "Kipling, Rudyard", 1902),
    GutenbergBook(1450, "Pollyanna", "Porter, Eleanor H.", 1913),
    GutenbergBook(157, "Daddy-Long-Legs", "Webster, Jean", 1912),
    GutenbergBook(67098, "Winnie-the-Pooh", "Milne, A. A.", 1926),
    # Translated fiction
    GutenbergBook(5200, "Metamorphosis", "Kafka, Franz", 1915),
    GutenbergBook(2500, "Siddhartha", "Hesse, Hermann", 1922),
    # Non-fiction
    GutenbergBook(408, "The Souls of Black Folk", "Du Bois, W. E. B.", 1903),
    GutenbergBook(2376, "Up from Slavery: An Autobiography", "Washington, Booker T.", 1901),
    GutenbergBook(15489, "Dream Psychology: Psychoanalysis for Beginners", "Freud, Sigmund", 1920),
    GutenbergBook(3825, "Pygmalion", "Shaw, Bernard", 1913),
)

# --- Old religious works, in translation -------------------------------------

RELIGIOUS_TRANSLATED_BOOKS: Tuple[GutenbergBook, ...] = (
    # Jewish and Christian scripture
    GutenbergBook(10, "The King James Version of the Bible", "", 1611, "Hebrew/Greek -> English"),
    GutenbergBook(8294, "The World English Bible (WEB), Complete", "", 2000, "modern translation"),
    GutenbergBook(8300, "The Bible, Douay-Rheims, Complete", "", 1752, "from the Latin Vulgate"),
    GutenbergBook(124, "Deuterocanonical Books of the Bible: Apocrypha", "", 1611),
    GutenbergBook(77935, "The Book of Enoch", "", 1917, "from Ethiopic"),
    GutenbergBook(14368, "Hebraic Literature: Translations from the Talmud", "", 1901),
    # Christian devotional and theological classics
    GutenbergBook(
        3296, "The Confessions of St. Augustine", "Augustine, of Hippo", 1838, "from Latin"
    ),
    GutenbergBook(1653, "The Imitation of Christ", "Thomas, à Kempis", 1886, "from Latin"),
    GutenbergBook(17611, "Summa Theologica, Part I", "Thomas Aquinas", 1911, "from Latin"),
    # Islamic scripture
    GutenbergBook(2800, "The Koran (Al-Qur'an), Rodwell translation", "", 1861, "from Arabic"),
    GutenbergBook(7440, "The Koran (Al-Qur'an), Sale translation", "", 1734, "from Arabic"),
    # Hindu scripture and epic
    GutenbergBook(3283, "The Upanishads", "", 1879, "from Sanskrit (Max Müller)"),
    GutenbergBook(2388, "The Song Celestial; Or, Bhagavad-Gîtâ", "", 1885, "from Sanskrit"),
    GutenbergBook(15474, "The Mahabharata, Book 1: Adi Parva", "", 1896, "from Sanskrit"),
    GutenbergBook(24869, "The Rámáyan of Válmíki", "Valmiki", 1874, "from Sanskrit"),
    # Buddhist scripture
    GutenbergBook(2017, "Dhammapada, a Collection of Verses", "", 1881, "from Pali"),
    GutenbergBook(
        35895, "The Gospel of Buddha, Compiled from Ancient Records", "Carus, Paul", 1894
    ),
    # Chinese classics
    GutenbergBook(
        216, "The Tao Teh King, or the Tao and its Characteristics", "Laozi", 1891, "from Chinese"
    ),
    GutenbergBook(3330, "The Analects of Confucius", "Confucius", 1893, "from Chinese"),
    GutenbergBook(
        9394,
        "The Shih King, or, Book of Poetry",
        "",
        1876,
        "from Chinese (Legge)",
    ),
    GutenbergBook(
        12894,
        "Sacred Books of the East",
        "",
        1917,
        "anthology: Vedic hymns, Avesta, Buddhist and Confucian texts",
    ),
    # Norse and Egyptian
    GutenbergBook(
        14726, "The Elder Eddas and the Younger Eddas", "Snorri Sturluson", 1866, "from Old Norse"
    ),
    GutenbergBook(7145, "The Book of the Dead", "Budge, E. A. Wallis", 1895, "from Egyptian"),
)

# Words scripture capitalizes as a matter of reverence rather than because they
# are names.  Without this the capitalization test would drop exactly the
# vocabulary this corpus exists to supply.  Actual proper nouns (Christ, Jesus,
# Israel, Allah, Krishna) are deliberately absent: those are names.
RELIGIOUS_VOCABULARY: Tuple[str, ...] = (
    "god",
    "god's",
    "gods",
    "goddess",
    "lord",
    "lord's",
    "lords",
    "spirit",
    "spirits",
    "heaven",
    "heavens",
    "father",
    "son",
    "king",
    "kings",
    "priest",
    "priests",
    "prophet",
    "prophets",
    "angel",
    "angels",
    "temple",
    "scripture",
    "scriptures",
    "psalm",
    "psalms",
    "gospel",
    "law",
    "creator",
    "almighty",
    "holy",
)


# --- Early modern science, Newton to Einstein --------------------------------

# Works of science written in English by their authors, so the corpus measures
# period scientific prose rather than a translator's later idiom.  Translations
# are allowed when they are contemporaneous - within ten years of the original,
# which keeps the English of the same era: Lavoisier (French 1789, English
# 1790), Poincare (1902/1905) and Einstein (1916/1920).
#
# Boyle and Hooke sit just before Newton.  They are the Royal Society milieu
# Opticks came out of, and dropping them would start the corpus mid-conversation.
EARLY_MODERN_SCIENCE_BOOKS: Tuple[GutenbergBook, ...] = (
    # The founding generation
    GutenbergBook(
        22914,
        "The Sceptical Chymist: or Chymico-Physical Doubts & Paradoxes",
        "Boyle, Robert",
        1661,
    ),
    GutenbergBook(
        15491,
        "Micrographia: Some Physiological Descriptions of Minute Bodies",
        "Hooke, Robert",
        1665,
    ),
    GutenbergBook(
        33504,
        "Opticks: or, A Treatise of the Reflections, Refractions, Inflections and Colours of Light",
        "Newton, Isaac",
        1704,
    ),
    GutenbergBook(1408, "The Natural History of Selborne", "White, Gilbert", 1789),
    GutenbergBook(
        30775,
        "Elements of Chemistry, in a New Systematic Order",
        "Lavoisier, Antoine Laurent",
        1790,
        "translated from the 1789 French the following year",
    ),
    # Physics, chemistry and astronomy
    GutenbergBook(
        14986,
        "Experimental Researches in Electricity, Volume 1",
        "Faraday, Michael",
        1839,
    ),
    GutenbergBook(14474, "The Chemical History of a Candle", "Faraday, Michael", 1861),
    GutenbergBook(14000, "Six Lectures on Light", "Tyndall, John", 1873),
    GutenbergBook(27378, "The Story of the Heavens", "Ball, Robert S.", 1885),
    GutenbergBook(28613, "Pioneers of Science", "Lodge, Oliver", 1893),
    GutenbergBook(
        4065,
        "Side-Lights on Astronomy and Kindred Fields of Popular Science",
        "Newcomb, Simon",
        1906,
    ),
    GutenbergBook(6630, "Curiosities of the Sky", "Serviss, Garrett P.", 1909),
    GutenbergBook(
        17149,
        "Creative Chemistry: Descriptive of Recent Achievements in the Chemical Industries",
        "Slosson, Edwin E.",
        1919,
    ),
    GutenbergBook(
        5001,
        "Relativity: The Special and General Theory",
        "Einstein, Albert",
        1916,
        "translated from German - the corpus's endpoint, kept despite that",
    ),
    GutenbergBook(29782, "Space, Time and Gravitation", "Eddington, Arthur", 1920),
    # Geology, biology and natural history
    GutenbergBook(
        33224,
        "Principles of Geology: or, The Modern Changes of the Earth and its Inhabitants",
        "Lyell, Charles",
        1830,
    ),
    GutenbergBook(944, "The Voyage of the Beagle", "Darwin, Charles", 1839),
    GutenbergBook(
        32021,
        "Island Life; Or, The Phenomena and Causes of Insular Faunas and Floras",
        "Wallace, Alfred Russel",
        1880,
    ),
    GutenbergBook(1228, "On the Origin of Species", "Darwin, Charles", 1859),
    GutenbergBook(2931, "Evidence as to Man's Place in Nature", "Huxley, Thomas Henry", 1863),
    GutenbergBook(16729, "Lay Sermons, Addresses and Reviews", "Huxley, Thomas Henry", 1870),
    GutenbergBook(2440, "The Naturalist on the River Amazons", "Bates, Henry Walter", 1863),
    GutenbergBook(32540, "My First Summer in the Sierra", "Muir, John", 1911),
    # Medicine
    GutenbergBook(
        17366, "Notes on Nursing: What It Is, and What It Is Not", "Nightingale, Florence", 1859
    ),
    GutenbergBook(1566, "The Evolution of Modern Medicine", "Osler, William", 1921),
    # Mathematics and scientific method
    GutenbergBook(15114, "An Investigation of the Laws of Thought", "Boole, George", 1854),
    GutenbergBook(
        37157,
        "Science and Hypothesis",
        "Poincaré, Henri",
        1905,
        "translated from the 1902 French within three years",
    ),
    GutenbergBook(57532, "Passages from the Life of a Philosopher", "Babbage, Charles", 1864),
    GutenbergBook(41568, "An Introduction to Mathematics", "Whitehead, Alfred North", 1911),
    GutenbergBook(41654, "Introduction to Mathematical Philosophy", "Russell, Bertrand", 1919),
)

# Gutenberg IDs in this file that have NOT been checked against catalogue
# metadata, and so may point at a different book than the title claims.  It is
# empty: every ID here has been confirmed.  Add an ID here when writing an
# entry from memory, and clear it once
#
#   PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py \
#       --corpus <name> --verify
#
# reports it OK.  That check reads catalogue metadata only - a few KB per book,
# no book text.  It is worth running: of 35 IDs written from memory for the
# science list, 15 pointed at an unrelated book.
UNVERIFIED_IDS: FrozenSet[int] = frozenset()


# --- Registry ----------------------------------------------------------------

BOOK_LISTS: Dict[str, BookList] = {
    "19th_books": BookList(
        corpus_name="19th_books",
        description="Word frequency data from 19th century books",
        max_words=5000,
        books=NINETEENTH_CENTURY_BOOKS,
    ),
    "20th_books": BookList(
        corpus_name="20th_books",
        description="Word frequency data from 20th century books",
        max_words=5000,
        books=TWENTIETH_CENTURY_BOOKS,
    ),
    "early_modern_science": BookList(
        corpus_name="early_modern_science",
        description="Word frequency data from early modern science writing, Newton to Einstein",
        max_words=3000,
        books=EARLY_MODERN_SCIENCE_BOOKS,
    ),
    "religious_translated": BookList(
        corpus_name="religious_translated",
        description="Word frequency data from old religious works in English translation",
        max_words=3000,
        books=RELIGIOUS_TRANSLATED_BOOKS,
        always_vocabulary=RELIGIOUS_VOCABULARY,
    ),
}


def get_book_list(corpus_name: str) -> BookList:
    """Return the book list for ``corpus_name``.

    Raises:
        KeyError: If no book list is defined for that corpus.
    """
    if corpus_name not in BOOK_LISTS:
        known = ", ".join(sorted(BOOK_LISTS))
        raise KeyError(f"No book list for corpus {corpus_name!r} (known: {known})")
    return BOOK_LISTS[corpus_name]


def get_corpus_names() -> List[str]:
    """Names of every corpus with a book list."""
    return sorted(BOOK_LISTS)


def find_book(gutenberg_id: int) -> Optional[GutenbergBook]:
    """Return the book with ``gutenberg_id`` from any list, if present."""
    for book_list in BOOK_LISTS.values():
        for book in book_list.books:
            if book.gutenberg_id == gutenberg_id:
                return book
    return None
