"""Pydantic models: the JSON shapes going in and out of the app.

Part 1 is the shape we ask Gemini to return. Its JSON schema is sent to Gemini, and the
same class parses Gemini's answer, so the shape is defined in exactly one place.
Part 2 is what our API endpoints return.

Math format: formula and work are LaTeX (no $ signs). Text fields are normal sentences
with inline math written as $...$, e.g. "The dynamic range is $DR = 6$ V."
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------- LaTeX safety net ----------

# In JSON, "\f" means form feed and "\t" means tab. If Gemini writes LaTeX such as \frac or
# \times with a single backslash, JSON turns it into a control character + "rac" / "imes".
# Those control characters never belong in our text, so we turn them back into LaTeX.
_CONTROL_TO_LATEX = {"\t": "\\t", "\x0c": "\\f", "\x08": "\\b", "\r": "\\r", "\x0b": "\\v"}


def repair_latex(text: str, single_line: bool = False) -> str:
    """Undo JSON escapes that ate a LaTeX backslash. In one-line LaTeX, a newline was "\\n" too."""
    for control, latex in _CONTROL_TO_LATEX.items():
        text = text.replace(control, latex)
    if single_line:
        text = text.replace("\n", "\\n")  # e.g. \neq, \nu
    return text


# Gemini sometimes writes math like code. In LaTeX, "_" only puts the NEXT character in the
# subscript, so "x_max" shows as x with subscript m then "ax", and "new_interval" shows as
# "new" with subscript i then "nterval". "*" shows as an asterisk instead of a dot.
_LETTER_SUBSCRIPT = re.compile(r"(?<![\\A-Za-z])([A-Za-z])_([A-Za-z0-9]{2,})(?![A-Za-z0-9])")
_NAME_WITH_UNDERSCORE = re.compile(r"(?<![\\A-Za-z])([A-Za-z]{2,})_([A-Za-z]{2,})(?![A-Za-z0-9])")
_TIMES_STAR = re.compile(r"(?<![\^{])\s*\*\s*")


def tidy_latex(latex: str) -> str:
    """Fix code-style math so KaTeX shows it as meant: x_max -> x_{max},
    new_interval -> new\\_interval (one name), a*b -> a \\cdot b."""
    latex = _LETTER_SUBSCRIPT.sub(r"\1_{\2}", latex)
    latex = _NAME_WITH_UNDERSCORE.sub(r"\1\\_\2", latex)
    return _TIMES_STAR.sub(r" \\cdot ", latex)


# ---------- Part 1: what Gemini must return ----------


class ExtractedStep(BaseModel):
    text: str = Field(description="What this step does, in one short sentence.")
    formula: str = Field(description="The formula used, in LaTeX without $. Empty string if none.")
    work: list[str] = Field(
        description="The substitution and calculation in LaTeX without $, one line per item, "
        'e.g. ["DR = x_{max} - x_{min}", "= 3 - (-3) = 6"]. Empty list if nothing is computed.'
    )
    result: str = Field(description="The value obtained in this step, with units. Empty string if none.")
    reason: str = Field(description="Why this step is needed.")
    page_number: int = Field(
        description="The n of the '=== PAGE n ===' marker where this step or its result is shown. "
        "For AI-derived steps, the page where the problem is."
    )
    source_quote: str = Field(
        description="Plain text copied exactly, character for character, from that page's text "
        "that shows this step. Empty string when ai_derived is true."
    )
    ai_derived: bool = Field(
        description="true only if neither this step nor its result is shown in the slides."
    )

    @field_validator("formula")
    @classmethod
    def _repair_formula(cls, value: str) -> str:
        return repair_latex(value, single_line=True)

    @field_validator("work")
    @classmethod
    def _repair_work(cls, lines: list[str]) -> list[str]:
        return [repair_latex(line, single_line=True) for line in lines if line.strip()]

    @field_validator("text", "result", "reason")
    @classmethod
    def _repair_text(cls, value: str) -> str:
        return repair_latex(value)


class ExtractedProblem(BaseModel):
    title: str = Field(description="Short title of the example problem.")
    page_number: int = Field(
        description="The n of the '=== PAGE n ===' marker where the problem statement is shown."
    )
    given: str = Field(description="What is known in the problem.")
    asked: str = Field(description="What must be found.")
    concept: str = Field(description="The main concept or formula used.")
    steps: list[ExtractedStep] = Field(description="The solution steps, in order.")
    final_answer: str = Field(description="The final answer in one sentence, with value and units.")

    @field_validator("given", "asked", "concept", "final_answer")
    @classmethod
    def _repair_text(cls, value: str) -> str:
        return repair_latex(value)


class ExtractionResult(BaseModel):
    problems: list[ExtractedProblem] = Field(
        description="Example problems that already appear in the slides. Empty if there are none."
    )


# ---------- Part 2: what our API returns ----------


class StepOut(BaseModel):
    # from_attributes lets Pydantic read values straight from the database objects.
    model_config = ConfigDict(from_attributes=True)

    step_number: int
    text: str
    formula: str | None  # None for steps saved before worked calculations existed
    work: list[str]  # LaTeX lines; stored in the database as one text with a line per entry
    result: str | None
    reason: str
    page_number: int
    source_quote: str
    ai_derived: bool  # Gemini says: neither this step nor its result is in the slides
    quote_verified: bool  # our check found source_quote on that page

    @field_validator("work", mode="before")
    @classmethod
    def _split_work_lines(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [line for line in value.split("\n") if line.strip()]
        return value

    # Tidied when sent to the web app (not when saved), so results stored earlier display
    # correctly too.
    @field_validator("formula")
    @classmethod
    def _tidy_formula(cls, value: str | None) -> str | None:
        return tidy_latex(value) if value else value

    @field_validator("work")
    @classmethod
    def _tidy_work(cls, lines: list[str]) -> list[str]:
        return [tidy_latex(line) for line in lines]


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    title: str
    page_number: int | None  # page where the problem is stated (None only for very old rows)
    given: str
    asked: str
    concept: str
    steps: list[StepOut]
    final_answer: str | None


class ProblemsResponse(BaseModel):
    document_id: str  # the random public id used in web addresses
    filename: str
    page_count: int
    model_name: str | None  # the Gemini model that found these problems
    is_sample: bool  # a stored demo sample: opens without an AI call, can't be re-processed
    cached: bool  # True when the result came from the database, not a new Gemini call
    message: str
    problems: list[ProblemOut]


class SampleOut(BaseModel):
    document_id: str
    filename: str
    page_count: int
    problem_count: int
    model_name: str | None


class UploadResponse(BaseModel):
    document_id: str  # the random public id used in web addresses
    filename: str
    page_count: int
    pages_with_text: int
    status: str
    already_uploaded: bool  # True when this exact file was uploaded before
    warning: str | None = None
