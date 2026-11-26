"""SolveFirst API: the endpoints and the error handlers.

Flow:  POST /documents  ->  POST /documents/{id}/process  ->  GET /documents/{id}/problems
The web app also loads slide images from GET /documents/{id}/pages/{n}/image,
and the demo samples from GET /samples.

{id} is a document's random public id (e.g. "x7Qk2bE9..."), never the internal number,
so nobody can list other people's uploads by counting.

The endpoints are plain `def` (not `async def`) on purpose: PyMuPDF, PyMySQL and the
Gemini call are all blocking, and FastAPI runs plain `def` endpoints in a thread pool.
"""

import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from app.config import PROJECT_ROOT, settings
from app.database import Base, engine, get_db
from app.gemini import GeminiError, extract_problems
from app.models import Document, Page, Problem, Step, upgrade_old_tables, utc_now
from app.pdf_store import cached_pdf_path, copy_disk_pdfs_to_database, file_rows, is_stored
from app.pdf_text import (
    NotAPdfError,
    PageNotFoundError,
    UnreadablePdfError,
    extract_page_texts,
    render_page_png,
)
from app.quote_check import check_quote
from app.schemas import ExtractionResult, ProblemOut, ProblemsResponse, SampleOut, UploadResponse

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
        upgrade_old_tables(engine)  # adds columns introduced after the tables were created
        copy_disk_pdfs_to_database(engine)  # PDFs that so far exist only in uploads/
        logger.info("Database tables are ready.")
    except OperationalError:
        # Start anyway so /docs still opens; endpoints will answer 503 until TiDB is back.
        logger.error("Could not reach TiDB at startup. Restart the server once it is reachable.")
    yield


app = FastAPI(
    title="SolveFirst API",
    description="Upload lecture slides as a PDF and get their example problems explained step by step.",
    version="0.3.0",
    lifespan=lifespan,
)

# Uploads may be a little bigger than the PDF itself (the form adds a few headers).
MAX_REQUEST_BYTES = settings.max_upload_mb * 1024 * 1024 + 1024 * 1024


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Answer 413 at once when an upload declares a size over the limit, before reading it.

    The upload endpoint checks the real size again after reading, in case the declared size
    was missing or wrong. This middleware is added before CORS on purpose: middleware added
    later wraps the earlier ones, so CORS also wraps this answer and the browser can read it.
    """
    declared_size = request.headers.get("content-length", "")
    if request.method == "POST" and request.url.path == "/documents" and declared_size.isdigit():
        if int(declared_size) > MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413, content={"detail": f"File is larger than {settings.max_upload_mb} MB."}
            )
    return await call_next(request)


# CORS: browsers block a page on one address (the React app on port 5173) from calling an
# API on another address (port 8000) unless the API allows it. We allow only our frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


def get_document_or_404(db: Session, document_id: str) -> Document:
    """Load a document (by its public id) with its problems and steps, or answer 404."""
    query = (
        select(Document)
        .where(Document.public_id == document_id)
        .options(selectinload(Document.problems).selectinload(Problem.steps))
    )
    document = db.scalar(query)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def stored_pdf_path(db: Session, document: Document) -> Path:
    """The uploaded PDF on disk (rebuilt from TiDB if needed), or answer 410 if it is lost."""
    path = cached_pdf_path(db, document)
    if path is None:
        raise HTTPException(status_code=410, detail="The stored PDF file is missing. Upload the file again.")
    return path


def upload_response(document: Document, already_uploaded: bool) -> UploadResponse:
    pages_with_text = sum(1 for page in document.pages if page.text.strip())
    warning = None
    if pages_with_text == 0:
        warning = "No text could be extracted (is this a scanned PDF?). Quotes cannot be verified."
    return UploadResponse(
        document_id=document.public_id,
        filename=document.filename,
        page_count=document.page_count,
        pages_with_text=pages_with_text,
        status=document.status,
        already_uploaded=already_uploaded,
        warning=warning,
    )


def problems_response(document: Document, cached: bool) -> ProblemsResponse:
    return ProblemsResponse(
        document_id=document.public_id,
        filename=document.filename,
        page_count=document.page_count,
        model_name=document.model_name,
        is_sample=document.is_sample,
        cached=cached,
        message=document.message or "",
        problems=[ProblemOut.model_validate(problem) for problem in document.problems],
    )


def build_problem_rows(extraction: ExtractionResult, page_texts: list[str]) -> list[Problem]:
    """Turn Gemini's answer into database rows, running the quote check on every step."""
    problems = []
    for position, extracted in enumerate(extraction.problems, start=1):
        page_is_valid = 1 <= extracted.page_number <= len(page_texts)
        problem = Problem(
            position=position,
            title=extracted.title[:255],
            page_number=extracted.page_number if page_is_valid else None,
            given=extracted.given,
            asked=extracted.asked,
            concept=extracted.concept,
            final_answer=extracted.final_answer or None,
        )
        for step_number, step in enumerate(extracted.steps, start=1):
            problem.steps.append(
                Step(
                    step_number=step_number,
                    text=step.text,
                    formula=step.formula or None,
                    work="\n".join(step.work) or None,  # one LaTeX line per text line
                    result=step.result or None,
                    reason=step.reason,
                    page_number=step.page_number,
                    source_quote=step.source_quote,
                    # Two separate facts: Gemini's own label, and whether our check found the quote.
                    ai_derived=step.ai_derived,
                    quote_verified=check_quote(step.source_quote, step.page_number, page_texts),
                )
            )
        problems.append(problem)
    return problems


# ---------- Endpoints ----------


@app.get("/", include_in_schema=False)
def root():
    """Opening the server address in a browser goes straight to the interactive docs."""
    return RedirectResponse("/docs")


@app.get("/health", include_in_schema=False)
def health():
    """Used by the hosting platform to check that the server is up. Does not touch TiDB."""
    return {"status": "ok"}


@app.get("/samples", response_model=list[SampleOut], tags=["samples"])
def list_samples(db: Session = Depends(get_db)):
    """The demo samples: decks processed earlier whose stored results open without an AI call.

    This is the only list of documents the API offers. Other uploads are reachable only by
    someone who has their (random) link.
    """
    samples = db.scalars(
        select(Document)
        .where(Document.is_sample, Document.status == "processed")
        .options(selectinload(Document.problems))
        .order_by(Document.filename)
    ).all()
    return [
        SampleOut(
            document_id=document.public_id,
            filename=document.filename,
            page_count=document.page_count,
            problem_count=len(document.problems),
            model_name=document.model_name,
        )
        for document in samples
    ]


@app.post("/documents", response_model=UploadResponse, tags=["documents"])
def upload_document(file: UploadFile = File(..., description="A lecture slide deck as a PDF"),
                    db: Session = Depends(get_db)):
    """Upload a PDF and store it, together with its per-page text, in TiDB."""
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

    # The cached file's name is the file's SHA-256 fingerprint, so identical uploads share one file.
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    stored_path = f"uploads/{sha256}.pdf"
    disk_path = PROJECT_ROOT / stored_path
    if not disk_path.exists():
        disk_path.parent.mkdir(exist_ok=True)
        disk_path.write_bytes(pdf_bytes)

    existing = db.scalar(select(Document).where(Document.file_sha256 == sha256))
    if existing is not None:
        if not is_stored(db, existing):  # uploaded before PDFs were kept in TiDB
            existing.files = file_rows(pdf_bytes)
            db.commit()
        return upload_response(existing, already_uploaded=True)

    document = Document(
        filename=filename[:255],
        stored_path=stored_path,
        file_sha256=sha256,
        page_count=len(page_texts),
        status="uploaded",
    )
    document.pages = [Page(page_number=number, text=text) for number, text in enumerate(page_texts, start=1)]
    document.files = file_rows(pdf_bytes)  # the PDF itself, in 2 MB pieces
    db.add(document)
    db.commit()  # document, pages and PDF are saved together, or not at all
    logger.info("Document %s uploaded: %s pages.", document.id, document.page_count)
    return upload_response(document, already_uploaded=False)


@app.post("/documents/{document_id}/process", response_model=ProblemsResponse, tags=["documents"])
def process_document(
    document_id: str,
    force: bool = Query(
        False,
        description="Find the problems again even if this deck was already processed "
        "(for example with a newer GEMINI_MODEL). Replaces the stored result and uses Gemini quota.",
    ),
    db: Session = Depends(get_db),
):
    """Find the example problems in the slides with Gemini. Runs Gemini only once per document,
    unless force=true."""
    document = get_document_or_404(db, document_id)

    # Cache: a processed document is answered from TiDB, without calling Gemini again.
    if document.status == "processed" and not force:
        return problems_response(document, cached=True)

    # Samples are fixed demo results: nobody may overwrite them or spend quota on them.
    if document.is_sample:
        raise HTTPException(status_code=409, detail="Samples are stored results and can't be re-processed.")

    page_texts = [page.text for page in document.pages]
    pdf_bytes = stored_pdf_path(db, document).read_bytes()

    # Gemini can take a minute. Give the database connection back to the pool while we wait.
    db.close()
    extraction = extract_problems(pdf_bytes, page_texts)  # raises GeminiError on failure
    problems = build_problem_rows(extraction, page_texts)

    # Lock the document row and check again, in case a second click processed it meanwhile.
    # With force=true we save anyway: the new result replaces the old one. If Gemini failed
    # above, we never get here, so the old result stays untouched.
    document = db.scalar(select(Document).where(Document.public_id == document_id).with_for_update())
    if document.status != "processed" or force:
        document.problems = problems  # old problems (and their steps) are deleted
        document.status = "processed"
        document.message = f"Found {len(problems)} example problem(s)." if problems else NO_PROBLEMS_MESSAGE
        document.model_name = settings.gemini_model
        document.processed_at = utc_now()
        db.commit()  # all problems and steps are saved together, or not at all
        step_count = sum(len(p.steps) for p in problems)
        verified = sum(s.quote_verified for p in problems for s in p.steps)
        ai_derived = sum(s.ai_derived for p in problems for s in p.steps)
        logger.info(
            "Document %s processed: %s problems, %s steps, %s quotes verified, %s AI-derived.",
            document.id, len(problems), step_count, verified, ai_derived,
        )
        return problems_response(document, cached=False)

    db.commit()  # someone else saved first: release the lock and return their result
    return problems_response(get_document_or_404(db, document_id), cached=True)


@app.get("/documents/{document_id}/problems", response_model=ProblemsResponse, tags=["documents"])
def get_problems(document_id: str, db: Session = Depends(get_db)):
    """Return the stored problems and steps of a processed document."""
    document = get_document_or_404(db, document_id)
    if document.status != "processed":
        raise HTTPException(
            status_code=409,
            detail=f"Not processed yet. Call POST /documents/{document_id}/process first.",
        )
    return problems_response(document, cached=True)


@app.get(
    "/documents/{document_id}/pages/{page_number}/image",
    tags=["documents"],
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "The page as a PNG image"}},
)
def get_page_image(document_id: str, page_number: int, db: Session = Depends(get_db)):
    """Return one page of the uploaded PDF as a PNG image, to show the slide beside a step."""
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        png = render_page_png(stored_pdf_path(db, document), page_number)
    except PageNotFoundError:
        raise HTTPException(status_code=404, detail=f"This deck has no page {page_number}.")
    # A stored PDF never changes (its file name is its fingerprint), so browsers may keep the image.
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
