from dataclasses import dataclass
from typing import Optional

@dataclass
class Translation:
    """Represents a translation in a specific language."""
    text: str
    pronunciation: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class TranslationSet:
    """Represents translations across multiple languages."""
    chinese: Optional[Translation] = None
    french: Optional[Translation] = None
    spanish: Optional[Translation] = None
    german: Optional[Translation] = None
    portuguese: Optional[Translation] = None
    korean: Optional[Translation] = None
    swahili: Optional[Translation] = None
    lithuanian: Optional[Translation] = None
    vietnamese: Optional[Translation] = None

    def get_translations(self) -> dict:
        """Get a dictionary of available translations."""
        return {
            "chinese": self.chinese,
            "french": self.french,
            "spanish": self.spanish,
            "german": self.german,
            "portuguese": self.portuguese,
            "korean": self.korean,
            "swahili": self.swahili,
            "lithuanian": self.lithuanian,
            "vietnamese": self.vietnamese
        }

    def has_translation(self, lang: str) -> bool:
        """Check if a translation exists for a specific language."""
        return getattr(self, lang, None) is not None
