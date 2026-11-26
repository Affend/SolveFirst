import katex from "katex";
import { Fragment, useMemo } from "react";

/**
 * Turn LaTeX into HTML with KaTeX.
 * - throwOnError: false -> broken LaTeX shows as red source text instead of crashing the page.
 * - KaTeX escapes its input, and its default trust: false blocks links and raw HTML,
 *   so inserting the result with dangerouslySetInnerHTML is safe.
 * - strict: "ignore" allows words like "bilangan" inside math without console warnings.
 */
function renderLatex(latex: string, displayMode: boolean): string {
  return katex.renderToString(latex, {
    displayMode,
    throwOnError: false,
    strict: "ignore",
    fleqn: true, // left-align display math instead of centering it
  });
}

/** One line of math on its own line, e.g. a formula or one line of the working. */
export function MathBlock({ latex }: { latex: string }) {
  const html = useMemo(() => renderLatex(latex, true), [latex]);
  return <div className="math-block" dangerouslySetInnerHTML={{ __html: html }} />;
}

/**
 * Normal text where parts written as $...$ are shown as math.
 * "The range is $DR = 6$ V." is split into ["The range is ", "DR = 6", " V."]:
 * the odd-numbered parts are math.
 */
export function RichText({ text }: { text: string }) {
  const parts = useMemo(() => text.split(/\$([^$]+)\$/g), [text]);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <span key={index} dangerouslySetInnerHTML={{ __html: renderLatex(part, false) }} />
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}
