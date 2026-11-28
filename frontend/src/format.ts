// Small display helpers shared by the pages.

import type { Problem } from "./types";

/** "1 step", "3 steps" */
export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** The page a problem comes from. Falls back to its first step for very old data. */
export function problemPage(problem: Problem): number | null {
  return problem.page_number ?? problem.steps[0]?.page_number ?? null;
}

/** The formulas a problem's steps use, each once, in the order they first appear. */
export function formulasUsed(problem: Problem): string[] {
  const formulas = problem.steps.map((step) => step.formula?.trim() ?? "").filter(Boolean);
  return [...new Set(formulas)];
}

/** Number of steps the AI filled in (not shown in the slides). */
export function countAiDerived(problem: Problem): number {
  return problem.steps.filter((step) => step.ai_derived).length;
}
