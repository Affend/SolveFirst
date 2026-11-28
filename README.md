# SolveFirst

A student uploads a lecturer's slide deck as a PDF. With no prompting, SolveFirst finds the
example problems already in the slides and shows each one **problem first**: what is given,
what is asked, the concept used, and numbered solution steps with reasons. Every step links to
the PDF page it came from. Steps the slides do not support are labeled **AI-derived**.

**Live demo:** _not deployed yet. The address will be added here after deployment (see
"Deploy to Render" below)._

Built for STACK 2026.
- **Milestone 1:** the backend (FastAPI + Gemini + TiDB).
- **Milestone 2:** the web app (React + Vite + TypeScript in `frontend/`).
- **Milestone 3:** stored demo samples, and deployment to Render.

## How it works

```
POST /documents                       store the PDF and the text of every page (PyMuPDF) in TiDB
POST /documents/{id}/process          send the PDF + page text to Gemini, get problems as JSON,
                                      check every quote against the page text, store in TiDB
GET  /documents/{id}/problems         read the stored problems and steps back from TiDB
GET  /documents/{id}/pages/{n}/image  one PDF page as a PNG image (shown beside each step)
GET  /samples                         the demo samples (stored results, no AI call)
GET  /health                          "is the server up?" for the hosting platform
```

`{id}` is a document's random public id (22 characters, e.g. `wuMCj3RFl3zoaQVjrnPqSg`), not a
counting number. Nobody can list other people's uploads by trying 1, 2, 3, and the only list the
API offers is `/samples`.

The web app in `frontend/` only talks to these endpoints. It never calls Gemini or TiDB directly.

**Each step shows the full working.** Gemini returns, per step:
- `text`: what the step does
- `formula`: LaTeX
- `work`: the substitution and calculation in LaTeX, one line per item
- `result`: the value, with units
- `reason`
- `page_number` and `source_quote`

Each problem also gets a `final_answer`. Text fields write inline math as `$...$`. The web app
renders all math with KaTeX, and lists each problem's formulas once under **Formulas used**
(collected from its steps), before the working.

The prompt requires a formula, working and result for every step that computes something. Leaving
them empty is allowed only for steps that compute nothing, and every problem with a calculation
must have at least one formula. Decks processed before worked calculations were added have no
formulas; run **Find problems again** on them.

**Two separate labels per step:**
- `ai_derived` comes from Gemini: neither the step nor its result is shown in the slides. The
  app shows a yellow **AI-derived** label.
- `quote_verified` is our own check: was `source_quote` found in the text PyMuPDF extracted from
  that page? When it is false (and the step is not AI-derived), the app shows a subtle "Page
  reference not auto-verified" note. This usually means the slide's formula is an image or an
  equation object whose text PyMuPDF cannot read.

**The quote check** (`app/quote_check.py`) tries four ways, strictest first:
1. Exact text, ignoring case, spacing, curly quotes and ligatures.
2. Fuzzy text for long quotes (a typo is allowed).
3. Compact math: both sides without spaces and the notation that PDF text loses (fraction bars,
   `^`, braces, LaTeX commands), with symbols unified (`>=`/`≥`, all minus signs, `Δ`, `π`).
4. Numbers: the quote's numbers (at least 2) appear on the page in the same order.

**Cache:** each document is sent to Gemini only once. Processing again returns the stored
result with `"cached": true`. Uploading the exact same file again returns the existing
document (`"already_uploaded": true`), so it is not processed twice.

**Running a deck again:** to redo a processed deck on purpose, for example after switching
`GEMINI_MODEL` to a stronger model, use **Find problems again** on the problem list page, or call
`POST /documents/{id}/process?force=true`. The new result replaces the old one, and if Gemini
fails, the old result stays untouched.

| File | What it does |
|---|---|
| `app/main.py` | The endpoints, CORS, and the error handlers |
| `app/config.py` | Reads `.env` once (secrets are never printed) |
| `app/database.py` | TiDB connection with SSL, same setup as `test_tidb.py` |
| `app/models.py` | The four tables: `documents`, `pages`, `problems`, `steps` |
| `app/schemas.py` | JSON shapes: what Gemini must return, and what our API returns |
| `app/pdf_text.py` | Checks the file is a real PDF, extracts text per page, renders a page as an image |
| `app/gemini.py` | The fixed instruction and the single Gemini call |
| `app/quote_check.py` | Verifies each step's quote against its page |
| `frontend/src/api.ts` | Every call from the web app to the backend, with plain-English errors |
| `frontend/src/pages/` | The three screens: upload, problem list, solution view |
| `frontend/src/components/` | Shared pieces: page frame, error box, slide panel, math (KaTeX) |
| `frontend/src/styles.css` | All styling (phone first, two columns on laptops) |

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
   - `TIDB_CA_PATH` (optional): leave it empty, and the backend uses the certificates from the
     `certifi` package, which include ISRG Root X1, the one TiDB Cloud uses. To use a file
     instead, download <https://letsencrypt.org/certs/isrgrootx1.pem> into a `certs` folder and
     set `TIDB_CA_PATH=certs/isrgrootx1.pem`.

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

## Run the app (backend + frontend) on Windows

You need **two terminals**: one for the backend, one for the web app.

1. Install Node.js LTS once (skip if `node --version` already works):

   ```powershell
   winget install OpenJS.NodeJS.LTS
   ```

2. **Terminal 1, the backend**, from the project folder:

   ```powershell
   conda activate solvefirst
   uvicorn app.main:app --reload
   ```

3. **Terminal 2, the web app**, from the project folder:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

   `npm install` is needed only the first time, and after someone changes `frontend/package.json`.

4. Open <http://localhost:5173> in your browser.

**Demo walkthrough:**
1. Choose a slide PDF and click **Find example problems**. A new deck can take 1–3 minutes.
   A deck that was already processed comes back instantly from the database.
2. Click **See the problems**. You see every example problem with the page it comes from.
3. Open a problem: Given, Asked, Concept, Formulas used, then the numbered steps with their reasons.
4. Click **Page N** on any step to show that slide beside the explanation. On a phone, the slide
   opens full screen; tap **Close** to go back. Steps labeled **AI-derived** are not shown in
   the slides and should be checked.
5. The problem list shows which Gemini model found the problems. **Find problems again** runs
   the deck again with the current `GEMINI_MODEL` (asks first, because it uses Gemini quota).

**Good to know:**
- The web app runs on port 5173, and the backend only accepts browser requests from that address
  (CORS). If you need another address, set `FRONTEND_ORIGINS` in `.env` (comma-separated), for
  example `FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000`.
- If the backend is not at `http://127.0.0.1:8000`, copy `frontend/.env.example` to
  `frontend/.env.local` and change `VITE_API_URL`.
- Check the frontend code with `npm run build` (includes the TypeScript check) and `npm run lint`.

## Demo samples

Samples are decks processed earlier whose results are stored. They appear on the upload page
under **"No PDF at hand? Try a sample"**, open instantly without calling Gemini, and always show
a **"Stored sample result"** label. That keeps the demo working even when Gemini is out of quota
or overloaded.

Mark samples from the project folder (with the `solvefirst` environment active):

```powershell
python -m app.samples list
```

```powershell
python -m app.samples add <document id>
```

```powershell
python -m app.samples remove <document id>
```

`<document id>` is the id in the web address (`/documents/<document id>`). Local and deployed
servers share the same TiDB, so a sample you add locally appears on the live site too.

Samples are **read-only**: `process?force=true` on a sample answers 409, and the web app hides
**Find problems again** for them, so nobody can spend quota on them or overwrite them during the
demo. To update a sample, `remove` it, click **Find problems again**, then `add` it again.

Sample slides are publicly visible on the live site. Only use decks you have permission to show.

## Deploy to Render

Both parts run on Render's free plan, defined in [`render.yaml`](render.yaml):
- `solvefirst-api`: the FastAPI backend, a free web service.
- `solvefirst-web`: the React app, a free static site.

| Option | Cost | Good | Bad |
|---|---|---|---|
| **Render free (used)** | $0 | one account, one file, deploys from GitHub | sleeps after 15 min idle, then about 1 minute to wake up; slow CPU |
| Railway Hobby | about $10/month | always on, persistent disk | needs a card, costs money |

**Before deploying:**
1. Rotate the Gemini API key and the TiDB password if they were ever committed. Put the new
   values in your local `.env` and in Render, never in the repo.
2. Push the code to GitHub (private repos work).

**Steps:**
1. In Render: **New → Blueprint**, connect GitHub, and pick this repository.
2. Render reads `render.yaml` and asks for each value marked `sync: false`:

   | Variable | Service | Value |
   |---|---|---|
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | api | as in your `.env` |
   | `TIDB_HOST`, `TIDB_PORT`, `TIDB_USER`, `TIDB_PASSWORD`, `TIDB_DATABASE` | api | as in your `.env` |
   | `FRONTEND_ORIGINS` | api | the web app's address, e.g. `https://solvefirst-web.onrender.com` |
   | `VITE_API_URL` | web | the backend's address, e.g. `https://solvefirst-api.onrender.com` |

   `TIDB_CA_PATH` is not needed: the backend uses `certifi`. `MAX_UPLOAD_MB` is set to 20.
3. If you didn't know the two addresses yet, fill them in once both services exist
   (**Environment** tab of each service), then redeploy the web app, because `VITE_API_URL`
   is baked in when the app is built.
4. Open the web app's address and try a sample.

**On demo day:** the free backend sleeps after 15 minutes without visitors, and the first request
then takes about a minute. Open the site (or the backend's `/health`) 2–3 minutes before you present.

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
   Set `force` to `true` to call Gemini again and replace the stored result.
5. **GET /documents/{document_id}/problems** → the same JSON, read from TiDB.

### See the rows in TiDB

In the TiDB Cloud console, open **SQL Editor** for your cluster and run the first query. Then
replace `1` in the others with the internal `id` of your deck (the number, not the `public_id`):

```sql
SELECT id, public_id, is_sample, filename, page_count, status, model_name, processed_at FROM documents;
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
| File larger than `MAX_UPLOAD_MB` (default 30; 20 on Render) | 413 | File is larger than 30 MB. (answered before the file is read) |
| Password-protected, damaged or empty PDF | 400 | This PDF could not be opened … |
| Unknown document id | 404 | Document not found. |
| Problems requested before processing | 409 | Not processed yet. Call POST …/process first. |
| Re-processing (`force=true`) a demo sample | 409 | Samples are stored results and can't be re-processed. |
| The PDF is missing both in TiDB and in `uploads/` | 410 | Upload the file again. |
| Gemini quota or rate limit | 429 | Gemini quota exceeded, with Google's limit and wait time, e.g. "Limit: 20 requests per day on Free Tier. Try again in 15h6m4s." |
| Gemini overloaded (Google-side 500/503) | 503 | Gemini is overloaded right now … |
| Gemini took longer than `GEMINI_TIMEOUT_SECONDS` (default 180) | 504 | Gemini took too long to respond. |
| Gemini rejected the API key, or sent an answer that does not match the schema | 502 | … |
| TiDB unreachable or login rejected | 503 | Database is unreachable … |

If Gemini fails, the document stays `uploaded` and you can simply run `/process` again.

**Free tier limit:** Gemini's free tier allows only a small number of requests per model per
day (20 at the time of writing). The limit resets at midnight US Pacific time (15:00 WIB).
To save quota, the app retries a failed Gemini call at most once, and only when Google is
overloaded (500/503) or slow, never on 429. Processing a deck again that is already processed
is free: it is served from TiDB.

**Which model:** we use `gemini-3.5-flash`. On the 19-page Arithmetic Coding deck it found all
8 example problems with correct working, while `gemini-3.1-flash-lite` found only 2. Flash-lite
is faster and is the fallback when 3.5-flash is overloaded (503) or out of quota: set
`GEMINI_MODEL` to it and process the deck again.

## Unit tests

```powershell
pytest
```

Runs offline tests for the quote check, the PDF helpers, the Gemini schema, PDF pieces, public
ids and the upload size limit. Nothing connects to Gemini or TiDB, but `test_deployment.py`
imports the app, so a `.env` (or the same environment variables) must exist.

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
- **Known limitation:** slides whose formulas are pictures have no text for PyMuPDF to read, so
  quotes from them cannot be verified. Those steps show "Page reference not auto-verified": they
  are not called AI-derived, but the student is told to check the slide. Old results (processed
  before this rule) keep their old labels until you click **Find problems again**.
- **KaTeX without a wrapper:** `frontend/src/components/Math.tsx` calls KaTeX directly. Broken
  LaTeX shows as red text instead of crashing the page. KaTeX escapes its input and blocks links
  and HTML, so inserting its output is safe.
- **Internal ids can jump (1, then 30001).** TiDB gives each of its servers a block of ids to
  hand out, so ids are unique and increasing but not consecutive. That is normal TiDB behavior.
  Web addresses never show these numbers; they use the random `public_id`.
- **PDFs are stored in TiDB, not only on disk.** Free hosting servers wipe their disk on every
  restart and sleep. Each PDF is saved in the `document_files` table in pieces of 2 MB (a TiDB
  row must stay under 6 MB). `uploads/` is only a cache: if a file is missing, `app/pdf_store.py`
  rebuilds it from TiDB.
- **Uploads are not publicly listable.** Documents are reachable only through their random
  22-character id, there is no list of uploads (only `/samples`), and no folder is served as
  static files.
- **The upload size limit is checked twice.** A small middleware answers 413 from the declared
  size before the file is read, and the endpoint checks the real size again after reading.
- **No certificate file on the server.** When `TIDB_CA_PATH` is empty, the TiDB connection uses
  `certifi`'s certificates, which include the one TiDB Cloud uses.
- **Secrets only in the hosting platform.** On Render there is no `.env`. Every value is set in
  the dashboard (`sync: false` in `render.yaml`).
