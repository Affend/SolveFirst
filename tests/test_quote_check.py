"""Offline tests for the quote check. Run with: pytest"""

from app.quote_check import check_quote, compact_math, is_quote_on_page, numbers_in

PAGE = """Example 2: Free fall
A ball is dropped from a height of 20 m.
Use  v² = 2gh   to find the final speed.
v = √(2 · 9.8 · 20) ≈ 19.8 m/s"""

# Made-up slide text with the same quirks PyMuPDF produces for equation objects:
# math-italic letters, a stacked fraction whose bar is lost (4 above 0.05),
# a Unicode minus sign, "≥", and a lost superscript (2^7 printed as "27").
MATH_PAGE = (
    "Solution of Example 3\n"
    "𝑦𝑛= 2 sin(0.5𝜋𝑛)\n"
    "Δ = 0.05\n"
    "𝑁−1 = 𝑅𝑎𝑛𝑔𝑒\n"
    "𝑆𝑡𝑒𝑝\n"
    "=\n"
    "4\n"
    "0.05 = 80; 𝑁= 81\n"
    "𝟐𝒌≥𝑁= 81\n"
    "27 = 128\n"
    "𝑘= 7 whole number\n"
)


# ---------- 1 and 2: text matching (unchanged behavior) ----------


def test_exact_quote_is_found():
    assert is_quote_on_page("A ball is dropped from a height of 20 m.", PAGE)


def test_case_and_whitespace_are_ignored():
    assert is_quote_on_page("use v² = 2gh to find\nthe FINAL speed", PAGE)


def test_ligature_and_curly_quotes_are_normalized():
    assert is_quote_on_page("“ﬁnal” value", "the \"final\" value")


def test_long_quote_with_small_typo_passes_fuzzy_match():
    assert is_quote_on_page("A ball is droped from a height of 20m", PAGE)


def test_short_quote_must_match():
    assert is_quote_on_page("v² = 2gh", PAGE)
    assert not is_quote_on_page("v² = 3gh", PAGE)


def test_made_up_quote_is_rejected():
    assert not is_quote_on_page("The car accelerates at 3 m/s² for ten seconds.", PAGE)


def test_empty_quote_is_rejected():
    assert not is_quote_on_page("", PAGE)


# ---------- 3: compact math matching ----------


def test_formula_with_lost_fraction_bar_is_found():
    assert is_quote_on_page("N - 1 = Range / Step = 4 / 0.05 = 80; N = 81", MATH_PAGE)


def test_greater_or_equal_written_two_ways_is_found():
    assert is_quote_on_page("2k >= N = 81", MATH_PAGE)
    assert is_quote_on_page(r"2k \geq N = 81", MATH_PAGE)


def test_spacing_around_equals_is_ignored():
    assert is_quote_on_page("k = 7 whole number", MATH_PAGE)


def test_delta_and_superscript_are_unified():
    assert is_quote_on_page(r"\Delta = 0.05", MATH_PAGE)
    assert is_quote_on_page("2^7 = 128", MATH_PAGE)


def test_compact_math_form():
    assert compact_math("L − 1 = 6 / 0.02") == "l-1=60.02"
    assert compact_math(r"\frac{6}{0.02} \geq x") == "60.02≥x"


# ---------- 4: number matching ----------


def test_numbers_in_same_order_pass():
    # The brackets in "y[n]" differ from the PDF text, but 2 and 0.5 appear in this order.
    assert is_quote_on_page(r"y[n] = 2 \sin(0.5 \pi n)", MATH_PAGE)


def test_decimal_comma_counts_as_point():
    assert numbers_in("Δ = 0,05 dan 4") == ["0.05", "4"]
    assert is_quote_on_page("step 0.05 for a range of 4 [rounded]", "Langkah 0,05; range 4")


def test_wrong_number_is_rejected():
    assert not is_quote_on_page("N - 1 = 4 / 0.05 = 90", MATH_PAGE)


def test_numbers_in_wrong_order_are_rejected():
    assert not is_quote_on_page("80 = 0.05 / 4 (backwards)", MATH_PAGE)


def test_single_number_is_not_enough():
    assert not is_quote_on_page("The answer is 128 levels exactly", MATH_PAGE)


# ---------- check_quote: page numbers ----------


def test_check_quote_on_the_right_page():
    assert check_quote("dropped from a height of 20 m", 1, [PAGE])


def test_check_quote_on_the_wrong_page():
    assert not check_quote("dropped from a height of 20 m", 1, ["Title slide", PAGE])


def test_check_quote_page_outside_deck():
    assert not check_quote("dropped from a height of 20 m", 5, [PAGE])
