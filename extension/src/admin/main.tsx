import React from "react";
import ReactDOM from "react-dom/client";

import { initTheme } from "../shared/theme";
import "../sidepanel/index.css";
import { AdminApp } from "./AdminApp";

initTheme();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("VisionLearn admin: #root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <AdminApp />
  </React.StrictMode>
);
