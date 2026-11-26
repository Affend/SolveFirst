import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import { getSamples, processDocument, toApiError, uploadDocument } from "../api";
import { ErrorBox } from "../components/ErrorBox";
import { Layout } from "../components/Layout";
import { SampleBadge } from "../components/SampleBadge";
import { ElapsedTime, StatusCard } from "../components/StatusCard";
import { plural } from "../format";
import type { SampleDeck } from "../types";

// The screen goes through these stages: idle -> uploading -> processing -> done (or error).
type Stage =
  | { name: "idle" }
  | { name: "uploading"; fileName: string }
  | { name: "processing"; fileName: string; startedAt: number }
  | { name: "done"; documentId: string; fileName: string; problemCount: number; warning: string | null }
  // documentId is set when the upload worked but processing failed, so "Try again" skips the upload.
  | { name: "error"; message: string; documentId: string | null };

export function UploadPage() {
  const [stage, setStage] = useState<Stage>({ name: "idle" });
  const [file, setFile] = useState<File | null>(null); // the last chosen PDF, kept for "Try again"
  const [isDragging, setIsDragging] = useState(false);
  const [samples, setSamples] = useState<SampleDeck[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const isBusy = stage.name === "uploading" || stage.name === "processing";

  // Load the demo samples once. If the server can't be reached, the section simply stays hidden.
  useEffect(() => {
    getSamples()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, []);

  /** Upload the PDF (unless it is already uploaded), then ask the backend to find its problems. */
  async function findProblems(pdf: File, alreadyUploadedId: string | null) {
    let documentId = alreadyUploadedId;
    let warning: string | null = null;
    try {
      if (documentId === null) {
        setStage({ name: "uploading", fileName: pdf.name });
        const upload = await uploadDocument(pdf);
        documentId = upload.document_id;
        warning = upload.warning;
      }
      setStage({ name: "processing", fileName: pdf.name, startedAt: Date.now() });
      const result = await processDocument(documentId);
      setStage({
        name: "done",
        documentId,
        fileName: pdf.name,
        problemCount: result.problems.length,
        warning,
      });
    } catch (error) {
      setStage({ name: "error", message: toApiError(error).message, documentId });
    }
  }

  /** A file was picked or dropped: check that it is a PDF, then start right away. */
  function start(chosen: File | undefined) {
    if (!chosen || isBusy) return;
    if (!chosen.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setStage({ name: "error", message: "Please choose a PDF file.", documentId: null });
      return;
    }
    setFile(chosen);
    void findProblems(chosen, null);
  }

  function onFileChosen(event: ChangeEvent<HTMLInputElement>) {
    start(event.target.files?.[0]);
    event.target.value = ""; // so the same file can be chosen again later
  }

  function onDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault(); // allows dropping
    if (!isBusy) setIsDragging(true);
  }

  function onDragLeave(event: DragEvent<HTMLElement>) {
    // Moving between elements inside the drop zone also fires this; only react when really leaving.
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragging(false);
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault(); // stop the browser from opening the PDF itself
    setIsDragging(false);
    start(event.dataTransfer.files[0]);
  }

  const chooseFile = () => fileInput.current?.click();

  return (
    <Layout>
      <section
        className={isDragging ? "hero is-dragging" : "hero"}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <h1>
          Learn from your slides, <span className="gradient-text">step by step</span>
        </h1>
        <p className="hero-sub">
          Upload your lecturer's slide deck. SolveFirst finds the example problems already in it and
          explains each one, with every step linked to its slide.
        </p>

        <input
          ref={fileInput}
          type="file"
          accept=".pdf,application/pdf"
          className="visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={onFileChosen}
        />

        {stage.name === "idle" && (
          <>
            <button type="button" className="select-button" onClick={chooseFile}>
              Select PDF file
            </button>
            <p className="drop-hint">or drop PDF here</p>
          </>
        )}

        {stage.name === "uploading" && (
          <div className="hero-panel">
            <StatusCard title={`Uploading ${stage.fileName}…`} />
          </div>
        )}

        {stage.name === "processing" && (
          <div className="hero-panel">
            <StatusCard title="Finding example problems in your slides…">
              This usually takes 1–3 minutes. Please keep this page open. Time so far:{" "}
              <ElapsedTime startedAt={stage.startedAt} />
            </StatusCard>
          </div>
        )}

        {stage.name === "done" && (
          <div className="hero-panel success-box" role="status">
            <p>
              <strong>
                {stage.problemCount > 0
                  ? `Done! Found ${plural(stage.problemCount, "example problem")}.`
                  : "Done. No example problems were found in this deck."}
              </strong>
            </p>
            <p className="muted">{stage.fileName}</p>
            {stage.warning && <p className="muted">{stage.warning}</p>}
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                onClick={() => navigate(`/documents/${stage.documentId}`)}
              >
                See the problems
              </button>
              <button type="button" className="button" onClick={chooseFile}>
                Upload another deck
              </button>
            </div>
          </div>
        )}

        {stage.name === "error" && (
          <div className="hero-panel">
            <ErrorBox
              message={stage.message}
              onRetry={file ? () => void findProblems(file, stage.documentId) : undefined}
            />
            <div className="button-row">
              <button type="button" className="button" onClick={chooseFile}>
                Choose another file
              </button>
            </div>
          </div>
        )}

        {isDragging && <p className="drop-overlay">Drop your PDF to start</p>}
      </section>

      {samples.length > 0 && (
        <section className="samples" aria-labelledby="samples-title">
          <h2 id="samples-title">No PDF at hand? Try a sample</h2>
          <p className="muted">
            These decks were processed earlier. Their results are stored, so they open instantly,
            without calling the AI.
          </p>
          <ul className="sample-list">
            {samples.map((sample) => (
              <li key={sample.document_id}>
                <Link className="problem-card sample-card" to={`/documents/${sample.document_id}`}>
                  <span className="problem-title">{sample.filename}</span>
                  <span className="problem-meta">
                    <span>{plural(sample.problem_count, "example problem")}</span>
                    <span>{plural(sample.page_count, "page")}</span>
                  </span>
                  <SampleBadge />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ol className="how-it-works" aria-label="How SolveFirst works">
        <li className="how-step">
          <span className="how-number">1</span>
          <h3>Upload your slides</h3>
          <p>Any lecture deck saved as a PDF.</p>
        </li>
        <li className="how-step">
          <span className="how-number">2</span>
          <h3>We find the examples</h3>
          <p>Only problems already in the slides. Nothing is invented.</p>
        </li>
        <li className="how-step">
          <span className="how-number">3</span>
          <h3>Learn step by step</h3>
          <p>Every step links to its slide. AI-filled steps are clearly labeled.</p>
        </li>
      </ol>
    </Layout>
  );
}
