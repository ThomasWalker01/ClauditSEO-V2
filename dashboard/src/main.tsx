import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
// The Structured data picture keeps its own sheet (brief v16a step AT-b):
// it is one screen's worth of layout, and folding 250 lines of grid and SVG
// rules into the shared file would put them in front of every other screen.
import "./schema_graph.css";
// And the crawl depth block, for the same reason (brief v16b).
import "./crawl_depth.css";
// And the Images part page's budget blocks (brief v16c).
import "./images_budget.css";
// And the Headings part page's outline ladder and template table (v16d).
import "./headings_outline.css";
// And the Audit pane's Score trend chart (brief v16f).
import "./score_trend.css";
// And the Indexability part's canonical chain cards (brief v16g).
import "./canonical_chains.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
