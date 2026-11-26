"""The quote check: does a step's quote really appear on its slide page?

Gemini gives each step a source_quote and a page_number. We look for that quote in the
text PyMuPDF extracted from that page, and store the answer as quote_verified.

This check does NOT decide whether a step is AI-derived; that is Gemini's own flag.
A failed check usually means the slide's formula is an image or an equation object whose
text PyMuPDF cannot read, so the app shows "Page reference not auto-verified" instead.

The check tries four ways, from strictest to loosest:
  1. exact text match (ignoring case and spacing)
  2. fuzzy match for long text quotes (allows a typo)
  3. compact math match (ignores spaces and notation that PDF text loses, like fraction bars)
  4. number match (the quote's numbers appear on the page in the same order)
"""

import re
import unicodedata

from rapidfuzz import fuzz

# Quotes shorter than this must match exactly. Fuzzy matching very short strings like
# "F = ma" would almost always find something "similar" and give false positives.
FUZZY_MIN_LENGTH = 20
# rapidfuzz score from 0 to 100. 90 allows small differences (a missing comma, a typo).
FUZZY_THRESHOLD = 90
# The compact math form of a quote must be at least this long (e.g. "b=9").
COMPACT_MIN_LENGTH = 3
# The number match needs at least this many numbers, or it would be far too easy to pass.
MIN_NUMBERS = 2

# Characters that look alike but differ in PDF text versus Gemini's output.
_LOOKALIKES = str.maketrans({
    "‘": "'", "’": "'",  # curly single quotes
    "“": '"', "”": '"',  # curly double quotes
    "–": "-", "—": "-",  # en dash, em dash
    "−": "-",                  # minus sign used in math
})

# LaTeX commands Gemini might put in a quote, turned into the symbol a PDF would contain.
# Any other command (\frac, \cdot, \text, \left ...) is simply dropped.
_LATEX_SYMBOLS = {"geq": "≥", "ge": "≥", "leq": "≤", "le": "≤", "neq": "≠", "ne": "≠",
                  "pi": "π", "delta": "δ"}

# Different ways of writing the same math symbol, all turned into one form (after lowercasing).
_MATH_SPELLINGS = [(">=", "≥"), ("<=", "≤"), ("!=", "≠"),
                   ("∆", "delta"), ("δ", "delta"), ("π", "pi")]

# Notation that PDF text often loses or changes: spaces, superscript/subscript marks,
# braces, LaTeX backslashes and dollar signs, fraction slashes, and multiplication dots.
_MATH_NOISE = re.compile(r"[\s^_{}$\\/*×·⋅∙]")

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def normalize(text: str) -> str:
    """Make two texts comparable: same Unicode form, lowercase, single spaces."""
    text = unicodedata.normalize("NFKC", text)  # "ﬁ" becomes "fi"; math letters 𝐿 𝜋 𝟐 become L π 2
    text = text.translate(_LOOKALIKES).lower()
    return re.sub(r"\s+", " ", text).strip()


def compact_math(text: str) -> str:
    """A stripped-down form for comparing formulas: "L − 1 = 6 / 0.02" becomes "l-1=60.02"."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\\([A-Za-z]+)", lambda m: _LATEX_SYMBOLS.get(m.group(1).lower(), ""), text)
    text = text.translate(_LOOKALIKES).lower()  # lowercasing also turns Δ into δ
    for spelling, unified in _MATH_SPELLINGS:
        text = text.replace(spelling, unified)
    return _MATH_NOISE.sub("", text)


def numbers_in(text: str) -> list[str]:
    """All numbers in reading order. A decimal comma counts as a point: "0,02" -> "0.02"."""
    return [n.replace(",", ".") for n in _NUMBER.findall(unicodedata.normalize("NFKC", text))]


def _appear_in_order(needles: list[str], haystack: list[str]) -> bool:
    """True if every needle is found in haystack, in the same order (gaps allowed)."""
    remaining = iter(haystack)
    # "needle in remaining" moves the iterator forward, so each search starts after the last find.
    return all(needle in remaining for needle in needles)


def is_quote_on_page(quote: str, page_text: str) -> bool:
    """True if the quote appears on the page, using the four checks described at the top."""
    quote_text = normalize(quote)
    page = normalize(page_text)
    if not quote_text or not page:
        return False

    # 1. Exact text.
    if quote_text in page:
        return True

    # 2. Fuzzy text: partial_ratio compares the quote with its best-matching stretch of the page.
    if len(quote_text) >= FUZZY_MIN_LENGTH and fuzz.partial_ratio(quote_text, page) >= FUZZY_THRESHOLD:
        return True

    # 3. Compact math: both sides simplified the same way, then compared exactly.
    compact_quote = compact_math(quote)
    if len(compact_quote) >= COMPACT_MIN_LENGTH and compact_quote in compact_math(page_text):
        return True

    # 4. Numbers: the quote's numbers appear on the page in the same order.
    quote_numbers = numbers_in(quote)
    return len(quote_numbers) >= MIN_NUMBERS and _appear_in_order(quote_numbers, numbers_in(page_text))


def check_quote(source_quote: str, page_number: int, page_texts: list[str]) -> bool:
    """quote_verified for one step: is source_quote on page page_number (counting from 1)?"""
    if not 1 <= page_number <= len(page_texts):
        return False
    return is_quote_on_page(source_quote, page_texts[page_number - 1])
