"""Offline tests for the LaTeX safety net and the API step shape. Run with: pytest"""

from app.schemas import ExtractedStep, StepOut, repair_latex


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


def test_step_out_splits_stored_work_into_lines():
    base = {"step_number": 1, "text": "t", "formula": None, "result": None, "reason": "r",
            "page_number": 1, "source_quote": "", "ai_derived": True, "quote_verified": False}
    assert StepOut.model_validate({**base, "work": "a = 1\n= 2"}).work == ["a = 1", "= 2"]
    assert StepOut.model_validate({**base, "work": None}).work == []
