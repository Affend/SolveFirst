"""The one Gemini call: send the slides, get back the example problems as JSON.

We use the Interactions API (client.interactions.create), which Google's docs recommend
for new projects, and the same API that test_gemini.py uses.
"""

import base64
import logging

from google import genai
from pydantic import ValidationError

from app.config import settings
from app.schemas import ExtractionResult

logger = logging.getLogger("solvefirst.gemini")

# The fixed instruction. The user never types a prompt; this text is the whole "prompt".
INSTRUCTION = """\
You are helping a student study from their lecturer's slides.

The attached PDF is a lecture slide deck. Below this instruction you also get the text
of every page, each page starting with a marker "=== PAGE n ===", where n is the PDF
page number counted from 1.

Task: find the EXAMPLE PROBLEMS that already appear in the slides (worked examples,
"Example", "Contoh soal", exercises with numbers, and so on) and present each one
"problem first".

Rules:
1. Only use problems that are already in the slides. Never invent a new problem.
   If the deck has no example problems, return {"problems": []}.
2. For each problem give: title (short), given (what is known), asked (what must be
   found), concept (the main idea or formula used), and steps (the solution in order).
3. For each step:
   - text: what to do in this step.
   - reason: why this step is done.
   - page_number: the n of the "=== PAGE n ===" marker of the page that shows this step.
     Use the PDF page number from the marker, NOT a slide number printed on the slide.
   - source_quote: a short piece of text (about one line) copied exactly, character
     for character, from that page's text below, that shows this step.
     Do not paraphrase, translate, or fix typos in the quote.
   - ai_derived: false if the step is shown in the slides; true if the slides skip it
     and you filled it in. For AI-derived steps, set source_quote to "" and page_number
     to the page where the problem is.
4. If a problem in the slides has no worked solution, you may still include it, but
   then every step you write must have ai_derived = true.
5. Write title, given, asked, concept, text and reason in the same language as the slides.
"""


class GeminiError(Exception):
    """Gemini failed. Carries the HTTP status and message our API should return."""

    status_code = 502
    message = "Gemini returned an unexpected response. Please try again."


class GeminiQuotaError(GeminiError):
    status_code = 429
    message = "Gemini quota exceeded. Wait a minute and try again."


class GeminiTimeoutError(GeminiError):
    status_code = 504
    message = "Gemini took too long to respond. Please try again."


class GeminiBusyError(GeminiError):
    status_code = 503
    message = "Gemini is overloaded right now (a problem on Google's side). Try again in a minute."


class GeminiAuthError(GeminiError):
    status_code = 502
    message = "Gemini rejected the API key. Check GEMINI_API_KEY in .env."


client = genai.Client(api_key=settings.gemini_api_key)


def build_page_text(page_texts: list[str]) -> str:
    """Join the extracted text of all pages, each with its "=== PAGE n ===" marker."""
    parts = []
    for number, text in enumerate(page_texts, start=1):
        parts.append(f"=== PAGE {number} ===\n{text.strip() or '(no text on this page)'}")
    return "\n\n".join(parts)


def _translate_error(exc: Exception) -> GeminiError:
    """Map an SDK exception to one of our GeminiError types, using only its status code and type."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    is_timeout = (
        isinstance(exc, TimeoutError)
        or "Timeout" in type(exc).__name__
        or isinstance(exc.__cause__, TimeoutError)
    )
    if is_timeout:
        return GeminiTimeoutError()
    if status == 429:
        return GeminiQuotaError()
    if status in (500, 503):
        return GeminiBusyError()
    if status in (401, 403) or (status == 400 and "api key" in str(exc).lower()):
        return GeminiAuthError()
    return GeminiError()


def extract_problems(pdf_bytes: bytes, page_texts: list[str]) -> ExtractionResult:
    """Send the PDF and its page text to Gemini and return the parsed problems."""
    try:
        interaction = client.interactions.create(
            model=settings.gemini_model,
            input=[
                {
                    # The PDF itself, so Gemini also sees equations, tables and diagrams.
                    "type": "document",
                    "data": base64.b64encode(pdf_bytes).decode("ascii"),
                    "mime_type": "application/pdf",
                },
                {"type": "text", "text": INSTRUCTION + "\n\n" + build_page_text(page_texts)},
            ],
            # Structured output: Gemini must answer with JSON that matches our Pydantic schema.
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": ExtractionResult.model_json_schema(),
            },
            # Do not keep the student's slides on Google's servers; we never continue the chat.
            store=False,
            timeout=settings.gemini_timeout_seconds,
        )
    except Exception as exc:
        # Log only the error type and status code, never the request or any key.
        logger.error("Gemini call failed (%s, status %s).", type(exc).__name__, getattr(exc, "status_code", None))
        raise _translate_error(exc) from exc

    try:
        return ExtractionResult.model_validate_json(interaction.output_text or "")
    except ValidationError as exc:
        logger.error("Gemini answer did not match the schema (%s errors).", exc.error_count())
        raise GeminiError() from exc
