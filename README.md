# SolveFirst

A student uploads a lecturer's slide deck as a PDF. With no prompting, SolveFirst finds the
example problems already in the slides and shows each one **problem first**: what is given,
what is asked, the concept used, and numbered solution steps with reasons. Every step links to
the PDF page it came from. Steps the slides do not support are labeled **AI-derived**.

Built for STACK 2026. This is **Milestone 1: the backend only** (no frontend yet).

## How it works

```
POST /documents                 save the PDF, extract the text of every page (PyMuPDF), store in TiDB
POST /documents/{id}/process    send the PDF + page text to Gemini, get problems as JSON,
                                check every quote against the page text, store in TiDB
GET  /documents/{id}/problems   read the stored problems and steps back from TiDB
```

**Why the "quote check" matters:** Gemini returns a `source_quote` and `page_number` for each
step. We look for that quote in the text PyMuPDF extracted from that page (ignoring case,
spacing, curly quotes and ligatures; long quotes may differ by a typo). If the quote is not
there, the step gets `quote_verified = false` and `ai_derived = true`. A step only counts as
"from the slides" when Gemini says so **and** the quote is really on that page.

**Cache:** each document is sent to Gemini only once. Processing again returns the stored
result with `"cached": true`. Uploading the exact same file again returns the existing
document (`"already_uploaded": true`), so it is not processed twice.

| File | What it does |
|---|---|
| `app/main.py` | The three endpoints and the error handlers |
| `app/config.py` | Reads `.env` once (secrets are never printed) |
| `app/database.py` | TiDB connection with SSL, same setup as `test_tidb.py` |
| `app/models.py` | The four tables: `documents`, `pages`, `problems`, `steps` |
| `app/schemas.py` | JSON shapes: what Gemini must return, and what our API returns |
| `app/pdf_text.py` | Checks the file is a real PDF, extracts text per page |
| `app/gemini.py` | The fixed instruction and the single Gemini call |
| `app/quote_check.py` | Verifies each step's quote against its page |

## Setup on Windows (PowerShell + Miniforge)

1. Create and activate a conda environment, then install the dependencies:

   ```powershell
   conda create -y -n solvefirst python=3.12
   conda activate solvefirst
   pip install -r requirements.txt
   ```

2. Create your `.env` from the template and fill in your own values:

   ```powershell
   Copy-Item .env.example .env
   ```

   - `GEMINI_API_KEY`: from Google AI Studio. `GEMINI_MODEL`: a model name from the Gemini
     models list (the code never hardcodes it).
   - `TIDB_*`: from the **Connect** dialog of your TiDB Cloud cluster.
   - `TIDB_CA_PATH`: the CA certificate file, e.g. `certs/isrgrootx1.pem` (relative to this folder).
     The certificate is the public ISRG Root X1 certificate; download it from
     <https://letsencrypt.org/certs/isrgrootx1.pem> into a `certs` folder.

   `.env` and `certs/` are in `.gitignore`. Never commit them.

3. Optional: check both connections with the smoke tests:

   ```powershell
   python test_tidb.py
   python test_gemini.py
   ```

## Run locally

From this folder, with the `solvefirst` environment active:

```powershell
uvicorn app.main:app --reload
```

The tables are created automatically the first time the server starts. Then open
<http://127.0.0.1:8000/docs> (opening <http://127.0.0.1:8000> redirects there).

## Test each endpoint in /docs

1. **POST /documents** → *Try it out* → choose a slide PDF under `file` → *Execute*.
   Note the `document_id` in the response. `pages_with_text` should be close to `page_count`;
   if it is 0 the PDF is a scan and quotes cannot be verified.
2. **GET /documents/{document_id}/problems** with that id → returns **409** "Not processed yet".
   That is expected before step 3.
3. **POST /documents/{document_id}/process** → *Execute*. This calls Gemini and can take
   30–120 seconds. The response has `"cached": false` and a list of `problems`, each with
   numbered `steps` that include `page_number`, `source_quote`, `ai_derived` and `quote_verified`.
   If the deck has no example problems, `problems` is `[]` and `message` says so.
4. Run **POST /documents/{document_id}/process** again → instant, `"cached": true`, no Gemini call.
5. **GET /documents/{document_id}/problems** → the same JSON, read from TiDB.

### See the rows in TiDB

In the TiDB Cloud console, open **SQL Editor** for your cluster and run (replace `1` with your id):

```sql
SELECT id, filename, page_count, status, message, model_name, processed_at FROM documents;
SELECT page_number, LEFT(text, 80) AS text_start FROM pages WHERE document_id = 1;
SELECT id, position, title, concept FROM problems WHERE document_id = 1;
SELECT s.problem_id, s.step_number, s.page_number, s.ai_derived, s.quote_verified, LEFT(s.text, 60) AS step
FROM steps s JOIN problems p ON p.id = s.problem_id
WHERE p.document_id = 1
ORDER BY s.problem_id, s.step_number;
```

## Errors

| Situation | HTTP status | Message |
|---|---|---|
| Not a PDF, or wrong file extension | 415 | Only PDF files are supported. |
| File larger than `MAX_UPLOAD_MB` (default 30) | 413 | File is larger than 30 MB. |
| Password-protected, damaged or empty PDF | 400 | This PDF could not be opened … |
| Unknown document id | 404 | Document not found. |
| Problems requested before processing | 409 | Not processed yet. Call POST …/process first. |
| Stored PDF file was deleted from `uploads/` | 410 | Upload the file again. |
| Gemini quota or rate limit | 429 | Gemini quota exceeded. Wait a minute and try again. |
| Gemini overloaded (Google-side 500/503) | 503 | Gemini is overloaded right now … |
| Gemini took longer than `GEMINI_TIMEOUT_SECONDS` (default 180) | 504 | Gemini took too long to respond. |
| Gemini rejected the API key, or sent an answer that does not match the schema | 502 | … |
| TiDB unreachable or login rejected | 503 | Database is unreachable … |

If Gemini fails, the document stays `uploaded` and you can simply run `/process` again.

## Unit tests

```powershell
pytest
```

Runs offline tests for the quote check (no Gemini or TiDB needed).

## Decisions worth explaining

- **Gemini Interactions API** (`client.interactions.create`): Google's docs recommend it for new
  projects. The model name always comes from `GEMINI_MODEL`.
- **We send both the PDF and its extracted text.** The PDF lets Gemini see equations and diagrams;
  the text, marked `=== PAGE n ===`, makes Gemini copy quotes from the exact text the quote
  check uses, and use PDF page numbers rather than slide numbers printed on the slides.
- **Structured output:** the Pydantic class `ExtractionResult` in `app/schemas.py` is turned into
  the JSON schema Gemini must follow, and the same class parses the answer.
- **`store=False`:** the student's slides are not kept on Google's servers after the call.
- **Plain `def` endpoints:** PyMuPDF, PyMySQL and Gemini are blocking libraries; FastAPI runs
  plain `def` endpoints in a thread pool, so the code stays simple.
- **Known limitation:** math whose PDF text comes out garbled cannot be verified, so those steps
  are labeled AI-derived. That errs on the safe side.
- **Ids can jump (1, then 30001).** TiDB gives each of its servers a block of ids to hand out,
  so ids are unique and increasing but not consecutive. That is normal TiDB behavior.
