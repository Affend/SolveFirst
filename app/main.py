"""SolveFirst API: the three endpoints and the error handlers.

Flow:  POST /documents  ->  POST /documents/{id}/process  ->  GET /documents/{id}/problems

The endpoints are plain `def` (not `async def`) on purpose: PyMuPDF, PyMySQL and the
Gemini call are all blocking, and FastAPI runs plain `def` endpoints in a thread pool.
"""

import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from app.config import PROJECT_ROOT, settings
from app.database import Base, engine, get_db
from app.gemini import GeminiError, extract_problems
from app.models import Document, Page, Problem, Step, utc_now
from app.pdf_text import NotAPdfError, UnreadablePdfError, extract_page_texts
from app.quote_check import label_step
from app.schemas import ExtractionResult, ProblemOut, ProblemsResponse, UploadResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("solvefirst")

NO_PROBLEMS_MESSAGE = (
    "No example problems were found in these slides. "
    "SolveFirst only shows problems that already appear in the deck."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts: make the uploads folder and the database tables."""
    settings.upload_dir.mkdir(exist_ok=True)
    try:
        Base.metadata.create_all(engine)  # only creates tables that do not exist yet
        logger.info("Database tables are ready.")
    except OperationalError:
        # Start anyway so /docs still opens; endpoints will answer 503 until TiDB is back.
        logger.error("Could not reach TiDB at startup. Restart the server once it is reachable.")
    yield


app = FastAPI(
    title="SolveFirst API",
    description="Upload lecture slides as a PDF and get their example problems explained step by step.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------- Error handlers: turn internal errors into clear JSON answers ----------


@app.exception_handler(OperationalError)
async def database_unreachable(request: Request, exc: OperationalError):
    # Log only the error type: driver messages contain the database host name.
    logger.error("Database error (%s).", type(exc.orig).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is unreachable. Check your internet connection and the TiDB settings in .env."},
    )


@app.exception_handler(GeminiError)
async def gemini_failed(request: Request, exc: GeminiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# ---------- Helpers ----------


def get_document_or_404(db: Session, document_id: int) -> Document:
    """Load a document with its problems and steps (3 queries in total), or answer 404."""
    query = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.problems).selectinload(Problem.steps))
    )
    document = db.scalar(query)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def upload_response(document: Document, already_uploaded: bool) -> UploadResponse:
    pages_with_text = sum(1 for page in document.pages if page.text.strip())
    warning = None
    if pages_with_text == 0:
        warning = "No text could be extracted (is this a scanned PDF?). Quotes cannot be verified."
    return UploadResponse(
        document_id=document.id,
        filename=document.filename,
        page_count=document.page_count,
        pages_with_text=pages_with_text,
        status=document.status,
        already_uploaded=already_uploaded,
        warning=warning,
    )


def problems_response(document: Document, cached: bool) -> ProblemsResponse:
    return ProblemsResponse(
        document_id=document.id,
        cached=cached,
        message=document.message or "",
        problems=[ProblemOut.model_validate(problem) for problem in document.problems],
    )


def build_problem_rows(extraction: ExtractionResult, page_texts: list[str]) -> list[Problem]:
    """Turn Gemini's answer into database rows, running the quote check on every step."""
    problems = []
    for position, extracted in enumerate(extraction.problems, start=1):
        problem = Problem(
            position=position,
            title=extracted.title[:255],
            given=extracted.given,
            asked=extracted.asked,
            concept=extracted.concept,
        )
        for step_number, step in enumerate(extracted.steps, start=1):
            quote_verified, ai_derived = label_step(
                step.ai_derived, step.source_quote, step.page_number, page_texts
            )
            problem.steps.append(
                Step(
                    step_number=step_number,
                    text=step.text,
                    reason=step.reason,
                    page_number=step.page_number,
                    source_quote=step.source_quote,
                    ai_derived=ai_derived,
                    quote_verified=quote_verified,
                )
            )
        problems.append(problem)
    return problems


# ---------- Endpoints ----------


@app.get("/", include_in_schema=False)
def root():
    """Opening the server address in a browser goes straight to the interactive docs."""
    return RedirectResponse("/docs")


@app.post("/documents", response_model=UploadResponse, tags=["documents"])
def upload_document(file: UploadFile = File(..., description="A lecture slide deck as a PDF"),
                    db: Session = Depends(get_db)):
    """Upload a PDF, save it in uploads/, and store its per-page text in TiDB."""
    filename = file.filename or "slides.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    pdf_bytes = file.file.read(max_bytes + 1)  # read one byte more than allowed to detect "too big"
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB.")

    try:
        page_texts = extract_page_texts(pdf_bytes)
    except NotAPdfError:
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")
    except UnreadablePdfError:
        raise HTTPException(
            status_code=400, detail="This PDF could not be opened (password-protected, damaged, or empty)."
        )

    # The file name on disk is the file's SHA-256 fingerprint, so identical uploads share one file.
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    stored_path = f"uploads/{sha256}.pdf"
    disk_path = PROJECT_ROOT / stored_path
    if not disk_path.exists():
        disk_path.write_bytes(pdf_bytes)

    existing = db.scalar(select(Document).where(Document.file_sha256 == sha256))
    if existing is not None:
        return upload_response(existing, already_uploaded=True)

    document = Document(
        filename=filename[:255],
        stored_path=stored_path,
        file_sha256=sha256,
        page_count=len(page_texts),
        status="uploaded",
    )
    document.pages = [Page(page_number=number, text=text) for number, text in enumerate(page_texts, start=1)]
    db.add(document)
    db.commit()  # document and all its pages are saved together, or not at all
    logger.info("Document %s uploaded: %s pages.", document.id, document.page_count)
    return upload_response(document, already_uploaded=False)


@app.post("/documents/{document_id}/process", response_model=ProblemsResponse, tags=["documents"])
def process_document(document_id: int, db: Session = Depends(get_db)):
    """Find the example problems in the slides with Gemini. Runs Gemini only once per document."""
    document = get_document_or_404(db, document_id)

    # Cache: a processed document is answered from TiDB, without calling Gemini again.
    if document.status == "processed":
        return problems_response(document, cached=True)

    page_texts = [page.text for page in document.pages]
    disk_path = PROJECT_ROOT / document.stored_path
    if not disk_path.exists():
        raise HTTPException(status_code=410, detail="The stored PDF file is missing. Upload the file again.")
    pdf_bytes = disk_path.read_bytes()

    # Gemini can take a minute. Give the database connection back to the pool while we wait.
    db.close()
    extraction = extract_problems(pdf_bytes, page_texts)  # raises GeminiError on failure
    problems = build_problem_rows(extraction, page_texts)

    # Lock the document row and check again, in case a second click processed it meanwhile.
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document.status != "processed":
        document.problems = problems
        document.status = "processed"
        document.message = f"Found {len(problems)} example problem(s)." if problems else NO_PROBLEMS_MESSAGE
        document.model_name = settings.gemini_model
        document.processed_at = utc_now()
        db.commit()  # all problems and steps are saved together, or not at all
        step_count = sum(len(p.steps) for p in problems)
        verified = sum(s.quote_verified for p in problems for s in p.steps)
        logger.info(
            "Document %s processed: %s problems, %s steps, %s quotes verified.",
            document_id, len(problems), step_count, verified,
        )
        return problems_response(document, cached=False)

    db.commit()  # someone else saved first: release the lock and return their result
    return problems_response(get_document_or_404(db, document_id), cached=True)


@app.get("/documents/{document_id}/problems", response_model=ProblemsResponse, tags=["documents"])
def get_problems(document_id: int, db: Session = Depends(get_db)):
    """Return the stored problems and steps of a processed document."""
    document = get_document_or_404(db, document_id)
    if document.status != "processed":
        raise HTTPException(
            status_code=409,
            detail=f"Not processed yet. Call POST /documents/{document_id}/process first.",
        )
    return problems_response(document, cached=True)
