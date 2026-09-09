import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProvider } from "./context";
import { App, AppErrorBoundary } from "./App";
import "../styles.css";
const root = document.getElementById("root");
if (!root) throw new Error("Root element is missing");
createRoot(root).render(
  <StrictMode>
    <AppErrorBoundary>
      <AppProvider>
        <App />
      </AppProvider>
    </AppErrorBoundary>
  </StrictMode>,
);
