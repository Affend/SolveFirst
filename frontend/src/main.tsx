import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProblemListPage } from "./pages/ProblemListPage";
import { SolutionPage } from "./pages/SolutionPage";
import { UploadPage } from "./pages/UploadPage";
import "katex/dist/katex.min.css"; // fonts and layout for math rendered with KaTeX
import "./styles.css";

// The three screens and their web addresses.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/documents/:documentId" element={<ProblemListPage />} />
        <Route path="/documents/:documentId/problems/:problemId" element={<SolutionPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
