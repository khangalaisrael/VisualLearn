import React from "react";
import ReactDOM from "react-dom/client";

import { initTheme } from "../shared/theme";
import { App } from "./App";
import "./index.css";

initTheme();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("VisionLearn AI: #root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
