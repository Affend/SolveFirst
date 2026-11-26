/** The visible label on every stored sample result. */
export function SampleBadge() {
  return (
    <span className="badge-sample" title="Processed earlier and saved. Opening it doesn't call the AI.">
      Stored sample result
    </span>
  );
}
