import { useCallback, useEffect, useState } from "react";
import { get } from "./api";
import type { Account, Limits } from "./types";

/** The user's broker accounts, kept live by the server's event stream (polling if that drops). */
export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await get<{ accounts: Account[]; limits: Limits }>("/api/accounts");
      setAccounts(r.accounts);
      setLimits(r.limits);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    let es: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | undefined;
    const startPolling = () => {
      if (!poll) poll = setInterval(load, 5000);
    };
    if (typeof EventSource !== "undefined") {
      es = new EventSource("/api/stream");
      es.addEventListener("accounts", (e) => {
        setAccounts(JSON.parse((e as MessageEvent).data));
        if (poll) {
          clearInterval(poll);
          poll = undefined;
        }
      });
      es.addEventListener("logout", () => es?.close());
      es.onerror = () => startPolling();     // EventSource reconnects by itself; poll meanwhile
    } else {
      startPolling();
    }
    return () => {
      es?.close();
      if (poll) clearInterval(poll);
    };
  }, [load]);

  const upsert = useCallback((a: Account) => {
    setAccounts((xs) => (xs ? (xs.some((x) => x.id === a.id) ? xs.map((x) => (x.id === a.id ? a : x)) : [...xs, a]) : [a]));
  }, []);
  const remove = useCallback((id: number) => setAccounts((xs) => (xs ? xs.filter((x) => x.id !== id) : xs)), []);

  return { accounts, limits, error, reload: load, upsert, remove };
}

/** Re-renders every second (for countdowns). */
export function useTicker(on: boolean) {
  const [, setN] = useState(0);
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setN((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [on]);
}
