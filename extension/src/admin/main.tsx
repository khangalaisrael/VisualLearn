import React from "react";
import ReactDOM from "react-dom/client";

import "../sidepanel/index.css";
import { AdminApp } from "./AdminApp";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("VisionLearn admin: #root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <AdminApp />
  </React.StrictMode>
);
