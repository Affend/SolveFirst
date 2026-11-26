// Every call to the SolveFirst backend lives here. The frontend never talks to Gemini or TiDB.

import type { ProblemsResult, SampleDeck, UploadResult } from "./types";

// Where the FastAPI backend runs. To change it, put VITE_API_URL=... in frontend/.env.local
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

/** An error whose message is clear enough to show to a student as it is. */
export class ApiError extends Error {
  status: number | null; // the HTTP status, or null when there was no answer from the server

  constructor(message: string, status: number | null) {
    super(message);
    this.status = status;
  }
}

/** Make sure any thrown value becomes an ApiError with a readable message. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError("Something went wrong. Please try again.", null);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    // fetch only throws when there is no answer at all: server stopped, wrong address, no network.
    throw new ApiError(
      "Can't reach the SolveFirst server. Make sure the backend is running, then try again.",
      null,
    );
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

/** The backend answers errors with {"detail": "<plain English message>"}. Use it when present. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // The answer was not JSON: use the general message below.
  }
  return `Something went wrong (error ${response.status}). Please try again.`;
}

export function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResult>("/documents", { method: "POST", body: form });
}

// documentId below is the random public id from the web address, e.g. "x7Qk2bE9...".

/** Find the problems with Gemini. force=true runs it again even if the deck was already processed. */
export function processDocument(documentId: string, force = false): Promise<ProblemsResult> {
  const query = force ? "?force=true" : "";
  return request<ProblemsResult>(`/documents/${encodeURIComponent(documentId)}/process${query}`, {
    method: "POST",
  });
}

export function getProblems(documentId: string): Promise<ProblemsResult> {
  return request<ProblemsResult>(`/documents/${encodeURIComponent(documentId)}/problems`);
}

/** The demo samples: stored results that open without an AI call. */
export function getSamples(): Promise<SampleDeck[]> {
  return request<SampleDeck[]>("/samples");
}

/** Address of one PDF page as a PNG image, ready for an <img src>. */
export function pageImageUrl(documentId: string, pageNumber: number): string {
  return `${API_URL}/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}/image`;
}
