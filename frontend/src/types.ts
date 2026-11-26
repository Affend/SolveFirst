// TypeScript versions of the JSON the backend sends. They mirror app/schemas.py.

// document_id is a random public id (e.g. "x7Qk2bE9..."), used in web addresses.

export interface UploadResult {
  document_id: string;
  filename: string;
  page_count: number;
  pages_with_text: number;
  status: "uploaded" | "processed";
  already_uploaded: boolean;
  warning: string | null;
}

// Math format: formula and work are LaTeX; text fields may contain inline math as $...$.
export interface Step {
  step_number: number;
  text: string;
  formula: string | null; // null for steps saved before worked calculations existed
  work: string[]; // one LaTeX line per item
  result: string | null;
  reason: string;
  page_number: number;
  source_quote: string;
  ai_derived: boolean; // Gemini: neither this step nor its result is shown in the slides
  quote_verified: boolean; // the quote was found in the page's text
}

export interface Problem {
  id: number;
  position: number;
  title: string;
  page_number: number | null; // page where the problem is stated
  given: string;
  asked: string;
  concept: string;
  steps: Step[];
  final_answer: string | null;
}

export interface ProblemsResult {
  document_id: string;
  filename: string;
  page_count: number;
  model_name: string | null; // the Gemini model that found these problems
  is_sample: boolean; // a stored demo sample: opens without an AI call, can't be re-processed
  cached: boolean;
  message: string;
  problems: Problem[];
}

// One card in the "Try a sample" section of the upload page.
export interface SampleDeck {
  document_id: string;
  filename: string;
  page_count: number;
  problem_count: number;
  model_name: string | null;
}
