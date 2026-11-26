"""The one Gemini call: send the slides, get back the example problems as JSON.

We use the Interactions API (client.interactions.create), which Google's docs recommend
for new projects, and the same API that test_gemini.py uses.
"""

import base64
import logging
import re

from google import genai
from google.genai import types
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
"problem first", with the full working.

Rules:
1. Only use problems that are already in the slides. Never invent a new problem.
   If the deck has no example problems, return {"problems": []}.
2. For each problem give: title (short), page_number (the n of the "=== PAGE n ==="
   marker where the problem statement is shown), given (what is known), asked (what must
   be found), concept (the main idea or formula used), steps (the solution in order), and
   final_answer (one sentence with the final value and its units).
3. For each step:
   - text: what this step does, in one short sentence.
   - formula: the formula used, in LaTeX. Empty string if the step uses no formula.
   - work: the substitution and calculation in LaTeX, one line per list item, for example
     ["DR = x_{max} - x_{min}", "= 3 - (-3) = 6"]. Empty list if nothing is computed.
   - result: the value obtained in this step, with units if any. Empty string if none.
   - reason: why this step is needed.
   - page_number: the n of the "=== PAGE n ===" marker of the page that shows this step
     or its result. Use the PDF page number from the marker, NOT a slide number printed
     on the slide.
   - source_quote: a short piece of text (about one line) copied exactly, character for
     character, from that page's text below. Copy it as plain text exactly as it appears
     in the page text, not rewritten as LaTeX. Do not paraphrase, translate, or fix typos.
   - ai_derived: true only if neither this step nor its result is shown in the slides.
     If the slides show the result but skip the arithmetic, ai_derived is false.
     For AI-derived steps, set source_quote to "" and page_number to the page where the
     problem is.
4. Every step that computes something must show the formula, the substituted values, and
   the result. Do not skip arithmetic, even when the slides skip it.
5. If a problem in the slides has no worked solution, you may still include it, but then
   every step you write must have ai_derived = true.
6. Math format: formula and each line of work are LaTeX without $ signs. In text, result,
   reason, given, asked, concept and final_answer, write normal sentences and put math
   inside $...$, for example "The dynamic range is $DR = 6$ V."
7. Follow the notation and the language of the slides.
"""


class GeminiError(Exception):
    """Gemini failed. Carries the HTTP status and message our API should return."""

    status_code = 502
    message = "Gemini returned an unexpected response. Please try again."

    def __init__(self, message: str | None = None):
        super().__init__()
        if message:
            self.message = message  # replace the default text with a more specific one


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


client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            # Every attempt counts against the free-tier daily limit (20 requests per day),
            # so try at most twice: the original request plus one retry.
            attempts=2,
            # Retry only when Google is overloaded or slow. Never retry 429 (quota):
            # retrying cannot help, and the student gets the real wait time instead.
            http_status_codes=[408, 500, 502, 503, 504],
        )
    ),
)


def quota_message(error_text: str) -> str:
    """Build a clear 429 message from Google's error text, including how long to wait.

    Google's text looks like: "... (limit: 20 requests per day on Free Tier).
    Please retry in 15h6m4s or upgrade your tier ..."
    """
    message = "Gemini quota exceeded."
    limit = re.search(r"limit: ([^)]+)\)", error_text)
    if limit:
        message += f" Limit: {limit.group(1)}."
    wait = re.search(r"retry in ([0-9hms.]+)", error_text)
    if wait:
        message += f" Try again in {wait.group(1).rstrip('.')}."
    else:
        message += " Wait a minute and try again."
    return message


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
        return GeminiQuotaError(quota_message(str(exc)))
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
