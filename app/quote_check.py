"""The quote check: proves that a step really comes from the slides.

Gemini gives each step a source_quote and a page_number. We look for that quote in the
text PyMuPDF extracted from that page. If it is not there, the step is labeled AI-derived,
so a student never sees an AI guess presented as the lecturer's own words.
"""

import re
import unicodedata

from rapidfuzz import fuzz

# Quotes shorter than this must match exactly. Fuzzy matching very short strings like
# "F = ma" would almost always find something "similar" and give false positives.
FUZZY_MIN_LENGTH = 20
# rapidfuzz score from 0 to 100. 90 allows small differences (a missing comma, a typo).
FUZZY_THRESHOLD = 90

# Characters that look alike but differ in PDF text versus Gemini's output.
_LOOKALIKES = str.maketrans({
    "‘": "'", "’": "'",  # curly single quotes
    "“": '"', "”": '"',  # curly double quotes
    "–": "-", "—": "-",  # en dash, em dash
    "−": "-",                  # minus sign used in math
})


def normalize(text: str) -> str:
    """Make two texts comparable: same Unicode form, lowercase, single spaces."""
    text = unicodedata.normalize("NFKC", text)  # e.g. the ligature "ﬁ" becomes "fi"
    text = text.translate(_LOOKALIKES).lower()
    return re.sub(r"\s+", " ", text).strip()


def is_quote_on_page(quote: str, page_text: str) -> bool:
    """True if the quote appears in the page text, exactly or (for longer quotes) nearly."""
    quote = normalize(quote)
    page_text = normalize(page_text)
    if not quote or not page_text:
        return False
    if quote in page_text:
        return True
    if len(quote) < FUZZY_MIN_LENGTH:
        return False
    # partial_ratio compares the quote with its best-matching stretch of the page.
    return fuzz.partial_ratio(quote, page_text) >= FUZZY_THRESHOLD


def label_step(
    gemini_says_ai_derived: bool, source_quote: str, page_number: int, page_texts: list[str]
) -> tuple[bool, bool]:
    """Return (quote_verified, ai_derived) for one step.

    Rule: a step only counts as "from the slides" when Gemini says so AND the quote
    is really on that page. Otherwise it is AI-derived.
    """
    page_exists = 1 <= page_number <= len(page_texts)
    quote_verified = page_exists and is_quote_on_page(source_quote, page_texts[page_number - 1])
    ai_derived = gemini_says_ai_derived or not quote_verified
    return quote_verified, ai_derived
