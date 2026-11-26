import { useState } from "react";
import { pageImageUrl } from "../api";

interface SlidePanelProps {
  documentId: string;
  pageNumber: number;
  openOnPhone: boolean; // on phones the panel is a full-screen view, opened by tapping "Page N"
  onClose: () => void;
}

/**
 * Shows one page of the uploaded PDF as an image.
 * Laptop: a column beside the explanation. Phone: a full-screen view with a Close button.
 * The difference is only CSS (see .slide-panel in styles.css).
 */
export function SlidePanel({ documentId, pageNumber, openOnPhone, onClose }: SlidePanelProps) {
  const src = pageImageUrl(documentId, pageNumber);
  // Remember which image finished loading (or failed), so a new page shows "Loading…" again.
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const isLoading = loadedSrc !== src && failedSrc !== src;

  return (
    <aside className={openOnPhone ? "slide-panel open" : "slide-panel"} aria-label="Slide">
      <div className="slide-panel-header">
        <h2>Slide page {pageNumber}</h2>
        <button type="button" className="button button-small close-button" onClick={onClose}>
          Close
        </button>
      </div>
      {failedSrc === src ? (
        <p className="muted">This page could not be loaded. Check that the backend is running.</p>
      ) : (
        <img
          src={src}
          alt={`Page ${pageNumber} of the uploaded slides`}
          className={isLoading ? "slide-image is-loading" : "slide-image"}
          onLoad={() => setLoadedSrc(src)}
          onError={() => setFailedSrc(src)}
        />
      )}
      {isLoading && <p className="muted">Loading page {pageNumber}…</p>}
    </aside>
  );
}
