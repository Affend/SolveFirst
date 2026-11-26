import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ErrorBox } from "../components/ErrorBox";
import { Layout } from "../components/Layout";
import { MathBlock, RichText } from "../components/Math";
import { SampleBadge } from "../components/SampleBadge";
import { SlidePanel } from "../components/SlidePanel";
import { problemPage } from "../format";
import { useProblems } from "../useProblems";

// Shown on hover over "Page reference not auto-verified".
const UNVERIFIED_HELP =
  "SolveFirst couldn't find this step's quote in the page's text, for example because the " +
  "formula on the slide is an image. Check the slide to confirm.";

export function SolutionPage() {
  const params = useParams();
  const documentId = params.documentId ?? "";
  const problemId = Number(params.problemId);
  const { state, retry } = useProblems(documentId);
  // The step whose slide is shown (null = show the page where the problem is stated).
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [slideOpenOnPhone, setSlideOpenOnPhone] = useState(false);

  // Start at the top when opening a problem (coming from a scrolled list).
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [problemId]);

  const backLink = (
    <Link to={`/documents/${documentId}`} className="back-link">
      ← All problems
    </Link>
  );

  if (state.status === "loading") {
    return (
      <Layout wide>
        <div className="status" role="status">
          <span className="spinner" aria-hidden="true" />
          <p>Loading solution…</p>
        </div>
      </Layout>
    );
  }

  if (state.status === "error") {
    return (
      <Layout wide>
        {backLink}
        <ErrorBox message={state.error.message} onRetry={retry} />
      </Layout>
    );
  }

  const problem = state.data.problems.find((p) => p.id === problemId);
  if (!problem) {
    return (
      <Layout wide>
        {backLink}
        <div className="notice">
          <p>We couldn't find this problem in the deck.</p>
        </div>
      </Layout>
    );
  }

  const shownStep = problem.steps.find((step) => step.step_number === activeStep);
  const shownPage = shownStep?.page_number ?? problemPage(problem);
  const hasAiSteps = problem.steps.some((step) => step.ai_derived);

  function showSlideFor(stepNumber: number) {
    setActiveStep(stepNumber);
    setSlideOpenOnPhone(true);
  }

  return (
    <Layout wide>
      {backLink}
      <div className="solution-layout">
        <article className="solution">
          <p className="eyebrow">
            Problem {problem.position}
            {problemPage(problem) !== null && ` · from page ${problemPage(problem)}`}
          </p>
          <h1>{problem.title}</h1>
          {state.data.is_sample && (
            <p className="sample-line">
              <SampleBadge />
            </p>
          )}

          <section className="field">
            <h2>Given</h2>
            <p>
              <RichText text={problem.given} />
            </p>
          </section>
          <section className="field">
            <h2>Asked</h2>
            <p>
              <RichText text={problem.asked} />
            </p>
          </section>
          <section className="field">
            <h2>Concept</h2>
            <p>
              <RichText text={problem.concept} />
            </p>
          </section>

          <section>
            <h2 className="steps-title">Steps</h2>
            {hasAiSteps && (
              <p className="ai-note" role="note">
                <span className="badge-ai">AI-derived</span> steps are not shown in the slides.
                SolveFirst added them to complete the solution, so check them against your notes or
                with your lecturer.
              </p>
            )}
            <ol className="steps">
              {problem.steps.map((step) => {
                const isActive = step.step_number === activeStep;
                return (
                  <li
                    key={step.step_number}
                    className={`step${isActive ? " is-active" : ""}${step.ai_derived ? " is-ai" : ""}`}
                  >
                    <span className="step-number" aria-hidden="true">
                      {step.step_number}
                    </span>
                    <div className="step-body">
                      {/* 1. What the step does */}
                      <p className="step-text">
                        <RichText text={step.text} />
                      </p>

                      {/* 2. The formula */}
                      {step.formula && (
                        <div className="step-formula">
                          <span className="math-label">Formula</span>
                          <MathBlock latex={step.formula} />
                        </div>
                      )}

                      {/* 3. The working, line by line, in a highlighted block */}
                      {step.work.length > 0 && (
                        <div className="work-block" aria-label="Working">
                          {step.work.map((line, index) => (
                            <MathBlock key={index} latex={line} />
                          ))}
                        </div>
                      )}

                      {/* 4. The result */}
                      {step.result && (
                        <p className="step-result">
                          <span className="math-label">Result:</span> <RichText text={step.result} />
                        </p>
                      )}

                      {/* 5. Why (smaller, secondary) */}
                      <p className="step-reason">
                        <strong>Why:</strong> <RichText text={step.reason} />
                      </p>

                      <div className="step-footer">
                        <button
                          type="button"
                          className="page-link"
                          aria-pressed={isActive}
                          onClick={() => showSlideFor(step.step_number)}
                        >
                          Page {step.page_number}
                        </button>
                        {step.ai_derived ? (
                          <span className="badge-ai">AI-derived</span>
                        ) : (
                          !step.quote_verified && (
                            <span className="unverified-note" title={UNVERIFIED_HELP}>
                              Page reference not auto-verified
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>

            {problem.final_answer && (
              <div className="final-answer">
                <h2>Final answer</h2>
                <p>
                  <RichText text={problem.final_answer} />
                </p>
              </div>
            )}
          </section>
        </article>

        {shownPage !== null && (
          <SlidePanel
            documentId={documentId}
            pageNumber={shownPage}
            openOnPhone={slideOpenOnPhone}
            onClose={() => setSlideOpenOnPhone(false)}
          />
        )}
      </div>
    </Layout>
  );
}
