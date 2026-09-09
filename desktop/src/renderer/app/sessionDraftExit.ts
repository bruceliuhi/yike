import { useEffect } from "react";
import { hasSessionContentAtRisk } from "./hooks";

/** Navigation keeps session drafts; closing their window does not. */
export function useSessionDraftExitProtection() {
  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      // Read at the event boundary, including edits made since the last render.
      // Do not use route guards: navigating within the app retains these drafts.
      if (!hasSessionContentAtRisk()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, []);
}
