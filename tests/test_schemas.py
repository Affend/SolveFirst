"""Offline tests for the LaTeX safety net and the API step shape. Run with: pytest"""

from app.schemas import ExtractedStep, StepOut, repair_latex, tidy_latex


def test_repair_latex_restores_eaten_backslashes():
    # "\frac" and "\times" parsed from JSON with a single backslash become control characters.
    assert repair_latex("\x0crac{6}{0.02} \times 2", single_line=True) == r"\frac{6}{0.02} \times 2"
    assert repair_latex("a \neq b", single_line=True) == r"a \neq b"


def test_repair_latex_keeps_real_newlines_in_text():
    assert repair_latex("line one\nline two") == "line one\nline two"


def test_gemini_step_is_repaired_when_parsed():
    step = ExtractedStep.model_validate({
        "text": "Compute the number of levels.",
        "formula": "L - 1 = \x0crac{DR}{\\Delta}",
        "work": ["L - 1 = \x0crac{6}{0.02} = 300", "  ", "L = 301"],
        "result": "$L = 301$ levels",
        "reason": "Needed for the number of bits.",
        "page_number": 22,
        "source_quote": "L - 1 = 300",
        "ai_derived": False,
    })
    assert step.formula == r"L - 1 = \frac{DR}{\Delta}"
    assert step.work == [r"L - 1 = \frac{6}{0.02} = 300", "L = 301"]  # empty line dropped


def test_tidy_latex_fixes_code_style_math():
    # A real formula Gemini returned for the arithmetic coding deck.
    assert (
        tidy_latex("new_interval = [low + P_{low}*range, low + P_{high}*range)")
        == r"new\_interval = [low + P_{low} \cdot range, low + P_{high} \cdot range)"
    )
    assert tidy_latex("DR = x_max - x_min") == "DR = x_{max} - x_{min}"
    assert tidy_latex("x_10") == "x_{10}"


def test_tidy_latex_leaves_proper_latex_alone():
    for latex in [
        r"H(1) = \sum_{n=0}^{3} h(n)e^{-j(\pi/2)n}",
        r"\omega_k = \frac{2\pi k}{N}",
        r"L - 1 = \frac{DR}{\Delta}",
        r"z^* = a - jb",
        r"x^{*}",
        r"\log_2 L",
    ]:
        assert tidy_latex(latex) == latex


def test_step_out_tidies_stored_math():
    base = {"step_number": 1, "text": "t", "result": None, "reason": "r",
            "page_number": 1, "source_quote": "", "ai_derived": False, "quote_verified": True}
    step = StepOut.model_validate({**base, "formula": "tag = (lower + upper)/2",
                                   "work": "T' = (T - low)*2\nx_max = 3"})
    assert step.formula == "tag = (lower + upper)/2"
    assert step.work == [r"T' = (T - low) \cdot 2", "x_{max} = 3"]


def test_step_out_splits_stored_work_into_lines():
    base = {"step_number": 1, "text": "t", "formula": None, "result": None, "reason": "r",
            "page_number": 1, "source_quote": "", "ai_derived": True, "quote_verified": False}
    assert StepOut.model_validate({**base, "work": "a = 1\n= 2"}).work == ["a = 1", "= 2"]
    assert StepOut.model_validate({**base, "work": None}).work == []
