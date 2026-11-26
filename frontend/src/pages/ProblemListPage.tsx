import { useState } from "react";
import { Link, useParams } from "react-router";
import { processDocument, toApiError } from "../api";
import { ErrorBox } from "../components/ErrorBox";
import { Layout } from "../components/Layout";
import { SampleBadge } from "../components/SampleBadge";
import { ElapsedTime, StatusCard } from "../components/StatusCard";
import { countAiDerived, plural, problemPage } from "../format";
import { useProblems } from "../useProblems";

// "Find problems again": idle, running (with a timer), or failed with a message.
type RerunState =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "error"; message: string };

export function ProblemListPage() {
  const documentId = useParams().documentId ?? "";
  const { state, retry } = useProblems(documentId);
  const [rerun, setRerun] = useState<RerunState>({ status: "idle" });

  /** Ask Gemini again (e.g. after switching to a stronger model). The old result stays if it fails. */
  async function findProblemsAgain() {
    const confirmed = window.confirm(
      "Find the problems in this deck again?\n\n" +
        "This replaces the current results, uses your Gemini quota, and can take 1–3 minutes.",
    );
    if (!confirmed) return;
    setRerun({ status: "running", startedAt: Date.now() });
    try {
      await processDocument(documentId, true);
      setRerun({ status: "idle" });
      retry(); // load the new results from the backend
    } catch (error) {
      setRerun({ status: "error", message: toApiError(error).message });
    }
  }

  if (state.status === "loading") {
    return (
      <Layout>
        <div className="narrow status" role="status">
          <span className="spinner" aria-hidden="true" />
          <p>Loading problems…</p>
        </div>
      </Layout>
    );
  }

  if (state.status === "error") {
    const { status, message } = state.error;
    return (
      <Layout>
        <div className="narrow">
          {status === 409 ? (
            <div className="notice">
              <p>This deck hasn't been processed yet. Upload it again to find its problems.</p>
              <Link to="/">Go to upload</Link>
            </div>
          ) : status === 404 || status === 422 ? (
            <div className="notice">
              <p>We couldn't find this slide deck.</p>
              <Link to="/">Upload a deck</Link>
            </div>
          ) : (
            <ErrorBox message={message} onRetry={retry} />
          )}
        </div>
      </Layout>
    );
  }

  const { data } = state;
  return (
    <Layout>
      <div className="narrow">
        <p className="eyebrow">Slide deck</p>
        <h1 className="deck-title">{data.filename}</h1>

        <div className="deck-actions">
          {data.is_sample && <SampleBadge />}
          {data.model_name && <span className="muted">Found with {data.model_name}</span>}
          {/* Samples are fixed demo results, so they can't be run again. */}
          {!data.is_sample && rerun.status !== "running" && (
            <button type="button" className="button button-small" onClick={findProblemsAgain}>
              Find problems again
            </button>
          )}
        </div>

        {rerun.status === "running" && (
          <StatusCard title="Finding the problems again…">
            This usually takes 1–3 minutes. The current results stay until the new ones are ready.
            Time so far: <ElapsedTime startedAt={rerun.startedAt} />
          </StatusCard>
        )}
        {rerun.status === "error" && <ErrorBox message={rerun.message} />}

        {data.problems.length === 0 ? (
          <div className="notice">
            <p>{data.message}</p>
            <Link to="/">Upload another deck</Link>
          </div>
        ) : (
          <>
            <p className="muted">
              Found {plural(data.problems.length, "example problem")} in this deck. Open one to see
              its solution step by step.
            </p>
            <ol className="problem-list">
              {data.problems.map((problem) => {
                const page = problemPage(problem);
                const aiCount = countAiDerived(problem);
                return (
                  <li key={problem.id}>
                    <Link
                      className="problem-card"
                      to={`/documents/${documentId}/problems/${problem.id}`}
                    >
                      <span className="eyebrow">Problem {problem.position}</span>
                      <span className="problem-title">{problem.title}</span>
                      <span className="problem-meta">
                        {page !== null && <span className="page-tag">Page {page}</span>}
                        <span>{plural(problem.steps.length, "step")}</span>
                        {aiCount > 0 && <span className="ai-count">{aiCount} AI-derived</span>}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>
    </Layout>
  );
}
