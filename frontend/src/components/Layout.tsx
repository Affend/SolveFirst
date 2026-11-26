import type { ReactNode } from "react";
import { Link } from "react-router";

interface LayoutProps {
  children: ReactNode;
  wide?: boolean; // the solution view needs room for the slide beside the explanation
}

/** The header, page frame and footer shared by every screen. */
export function Layout({ children, wide = false }: LayoutProps) {
  const container = wide ? "container container-wide" : "container";
  return (
    <>
      <header className="site-header">
        <div className={`${container} header-inner`}>
          <Link to="/" className="brand" aria-label="SolveFirst home">
            <BrandMark />
            <span>SolveFirst</span>
          </Link>
        </div>
      </header>
      <main className={`${container} page`}>{children}</main>
      <footer className={`${container} site-footer`}>SolveFirst · Built for STACK 2026</footer>
    </>
  );
}

/** Our logo: three rising bars, for "step by step". */
function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="brand-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4f7cff" />
          <stop offset="1" stopColor="#c35cf0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#brand-gradient)" />
      <rect x="7" y="18" width="5" height="7" rx="1.5" fill="#fff" />
      <rect x="13.5" y="13" width="5" height="12" rx="1.5" fill="#fff" />
      <rect x="20" y="8" width="5" height="17" rx="1.5" fill="#fff" />
    </svg>
  );
}
