"""Pydantic models: the JSON shapes going in and out of the app.

Part 1 is the shape we ask Gemini to return. Its JSON schema is sent to Gemini, and the
same class parses Gemini's answer, so the shape is defined in exactly one place.
Part 2 is what our API endpoints return.
"""

from pydantic import BaseModel, ConfigDict, Field

# ---------- Part 1: what Gemini must return ----------


class ExtractedStep(BaseModel):
    text: str = Field(description="What to do in this step.")
    reason: str = Field(description="Why this step is done.")
    page_number: int = Field(
        description="The n of the '=== PAGE n ===' marker where this step is shown. "
        "For AI-derived steps, the page where the problem is."
    )
    source_quote: str = Field(
        description="Text copied exactly, character for character, from that page that shows "
        "this step. Empty string when ai_derived is true."
    )
    ai_derived: bool = Field(
        description="false if the step is shown in the slides; true if you filled it in."
    )


class ExtractedProblem(BaseModel):
    title: str = Field(description="Short title of the example problem.")
    given: str = Field(description="What is known in the problem.")
    asked: str = Field(description="What must be found.")
    concept: str = Field(description="The main concept or formula used.")
    steps: list[ExtractedStep] = Field(description="The solution steps, in order.")


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
    reason: str
    page_number: int
    source_quote: str
    ai_derived: bool
    quote_verified: bool


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    title: str
    given: str
    asked: str
    concept: str
    steps: list[StepOut]


class ProblemsResponse(BaseModel):
    document_id: int
    cached: bool  # True when the result came from the database, not a new Gemini call
    message: str
    problems: list[ProblemOut]


class UploadResponse(BaseModel):
    document_id: int
    filename: str
    page_count: int
    pages_with_text: int
    status: str
    already_uploaded: bool  # True when this exact file was uploaded before
    warning: str | None = None
