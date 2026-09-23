/**
 * main.jsx - Application entry point.
 * Mounts <App/> into #root and loads the two app-wide stylesheets, in order:
 * global.css (the original style.css, reused verbatim) and then app-chrome.css,
 * which pulls the shared controls - toolbar search, filter dropdowns, status
 * pills, table numerals, list footer - onto the same visual system as the New
 * Job wizards. Order matters: app-chrome.css overrides global.css at equal
 * specificity, so it must come second.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./styles/global.css";
import "./styles/app-chrome.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
