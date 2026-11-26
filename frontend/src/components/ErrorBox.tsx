interface ErrorBoxProps {
  message: string;
  onRetry?: () => void; // when given, a "Try again" button is shown
}

/** A plain-language error message, optionally with a "Try again" button. */
export function ErrorBox({ message, onRetry }: ErrorBoxProps) {
  return (
    <div className="error-box" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
