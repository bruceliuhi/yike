import { useEffect, useMemo, useRef } from "react";
import { useApp } from "../../app/context";
import type { AccountState } from "../../domain/management";

/** An old request may finish, but cannot upload, save or notify in a new scope. */
export function useManagementScope(account?: AccountState, variant = "") {
  const { service, session } = useApp();
  const key = JSON.stringify([
    session.authenticated,
    session.userId,
    session.accountScope?.id,
    session.accountScope?.version,
    account?.userId,
    account?.accountScope?.id,
    account?.accountScope?.version,
    account?.spaceId,
    account?.revision,
    account?.device?.id,
    variant,
  ]);
  const identity = useMemo(() => ({}), [service, key]);
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
  return {
    key,
    identity,
    current,
    async run<T>(operation: () => Promise<T>): Promise<T | undefined> {
      if (!current()) return;
      try {
        return await operation();
      } catch (error) {
        if (current()) throw error;
      }
    },
  };
}
