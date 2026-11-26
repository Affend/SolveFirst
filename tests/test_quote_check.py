"""Offline tests for the quote check. Run with: pytest"""

from app.quote_check import is_quote_on_page, label_step

PAGE = """Example 2: Free fall
A ball is dropped from a height of 20 m.
Use  v² = 2gh   to find the final speed.
v = √(2 · 9.8 · 20) ≈ 19.8 m/s"""


def test_exact_quote_is_found():
    assert is_quote_on_page("A ball is dropped from a height of 20 m.", PAGE)


def test_case_and_whitespace_are_ignored():
    assert is_quote_on_page("use v² = 2gh to find\nthe FINAL speed", PAGE)


def test_ligature_and_curly_quotes_are_normalized():
    assert is_quote_on_page("“ﬁnal” value", "the \"final\" value")


def test_long_quote_with_small_typo_passes_fuzzy_match():
    assert is_quote_on_page("A ball is droped from a height of 20m", PAGE)


def test_short_quote_must_match_exactly():
    assert is_quote_on_page("v² = 2gh", PAGE)
    assert not is_quote_on_page("v² = 3gh", PAGE)


def test_made_up_quote_is_rejected():
    assert not is_quote_on_page("The car accelerates at 3 m/s² for ten seconds.", PAGE)


def test_empty_quote_is_rejected():
    assert not is_quote_on_page("", PAGE)


def test_label_step_verified_quote_stays_from_slides():
    assert label_step(False, "dropped from a height of 20 m", 1, [PAGE]) == (True, False)


def test_label_step_wrong_page_becomes_ai_derived():
    pages = ["Title slide", PAGE]
    assert label_step(False, "dropped from a height of 20 m", 1, pages) == (False, True)


def test_label_step_page_outside_deck_becomes_ai_derived():
    assert label_step(False, "dropped from a height of 20 m", 5, [PAGE]) == (False, True)


def test_label_step_gemini_ai_derived_stays_ai_derived():
    assert label_step(True, "", 1, [PAGE]) == (False, True)
