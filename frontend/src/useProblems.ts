import { useEffect, useState } from "react";
import { ApiError, getProblems, toApiError } from "./api";
import type { ProblemsResult } from "./types";

type ProblemsState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: ProblemsResult };

/**
 * Loads the problems of one deck. Used by the problem list and the solution view.
 * The backend reads them from TiDB, so this never spends Gemini quota.
 */
export function useProblems(documentId: string) {
  const [attempt, setAttempt] = useState(0); // bumping this number loads again ("Try again")
  const requestKey = `${documentId}#${attempt}`;
  // The last answer, labeled with the request it belongs to.
  const [answer, setAnswer] = useState<{ key: string; state: ProblemsState } | null>(null);

  useEffect(() => {
    let cancelled = false; // ignore a late answer if the student already left the page
    getProblems(documentId)
      .then((data) => {
        if (!cancelled) setAnswer({ key: requestKey, state: { status: "ready", data } });
      })
      .catch((error: unknown) => {
        if (!cancelled) setAnswer({ key: requestKey, state: { status: "error", error: toApiError(error) } });
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, requestKey]);

  // No answer yet for the current request (first visit, other deck, or "Try again"): loading.
  const state: ProblemsState =
    answer?.key === requestKey ? answer.state : { status: "loading" };
  return { state, retry: () => setAttempt((n) => n + 1) };
}
