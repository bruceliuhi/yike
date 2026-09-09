import { useEffect, useMemo, useRef } from "react";
import { useApp } from "../../app/context";

export function useTaskScope(variant = "") {
  const { service, session } = useApp();
  const identity = useMemo(
    () => ({}),
    [service, session.authenticated, session.userId, variant],
  );
  const latest = useRef(identity);
  latest.current = identity;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const current = () => mounted.current && latest.current === identity;
  return { identity, current };
}
