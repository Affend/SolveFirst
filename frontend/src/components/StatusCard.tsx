import { useEffect, useState, type ReactNode } from "react";

/** A card with a moving progress bar, shown while the backend is working. */
export function StatusCard({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="status-card" role="status">
      <p>
        <strong>{title}</strong>
      </p>
      {children && <p className="muted">{children}</p>}
      <div className="progress" aria-hidden="true" />
    </div>
  );
}

/** Shows minutes:seconds since `startedAt`, updated every second. */
export function ElapsedTime({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return (
    <span className="elapsed">
      {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
    </span>
  );
}
