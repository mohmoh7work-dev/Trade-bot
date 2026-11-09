import { useCallback, useEffect, useState } from "react";
import { get } from "../lib/api";
import { dateTime } from "../lib/format";
import type { Account, BotEvent } from "../lib/types";
import { Spinner } from "./Icons";
import { ErrorBox, Segmented, Sheet } from "./ui";

type Filter = "all" | "trades" | "decisions" | "errors";
const DOT: Record<string, string> = {
  trade: "bg-emerald-500", order: "bg-amber-500", signal: "bg-sky-500", decision: "bg-zinc-300",
  error: "bg-brand-600", bot: "bg-ink", log: "bg-amber-500",
};

export default function LogsSheet({ account, onClose }: { account: Account; onClose: () => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [events, setEvents] = useState<BotEvent[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const url = useCallback((before?: number) => "/api/accounts/" + account.id + "/events?limit=50" +
    (filter === "all" ? "" : "&kind=" + filter) + (before ? "&before=" + before : ""), [account.id, filter]);

  useEffect(() => {
    let alive = true;
    get<{ events: BotEvent[]; more: boolean }>(url()).then((r) => {
      if (!alive) return;
      setEvents((cur) => {
        if (!cur) return r.events;          // keep older pages already loaded; add the new lines on top
        const known = new Set(cur.map((e) => e.id));
        const fresh = r.events.filter((e) => !known.has(e.id));
        return fresh.length ? [...fresh, ...cur] : cur;
      });
      setMore((m) => m || r.more);
    }).catch((e) => alive && setError((e as Error).message));
    return () => { alive = false; };
  }, [url, account.last_event_id]);

  useEffect(() => { setEvents(null); setMore(false); }, [filter]);

  async function loadMore() {
    if (!events?.length) return;
    setLoadingMore(true);
    try {
      const r = await get<{ events: BotEvent[]; more: boolean }>(url(events[events.length - 1].id));
      setEvents([...events, ...r.events]);
      setMore(r.more);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <Sheet title="Activity log" subtitle={account.nickname + " · every decision, signal, order and trade"} onClose={onClose} wide>
      <Segmented label="Show" value={filter} onChange={setFilter}
        options={[{ value: "all", label: "All" }, { value: "trades", label: "Trades" },
          { value: "decisions", label: "Decisions" }, { value: "errors", label: "Problems" }]} />
      <div className="mt-4">
        <ErrorBox>{error}</ErrorBox>
        {events === null ? (
          <div className="flex justify-center py-10 text-brand-700"><Spinner className="h-6 w-6" /></div>
        ) : events.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink-faint">Nothing here yet.</p>
        ) : (
          <ol className="space-y-1">
            {events.map((e) => (
              <li key={e.id} className="flex gap-3 rounded-lg px-2 py-2 hover:bg-brand-50/60">
                <span className={"mt-1.5 h-2 w-2 shrink-0 rounded-full " + (DOT[e.kind] ?? "bg-zinc-300")} aria-hidden="true" />
                <div className="min-w-0">
                  <p className={"text-sm leading-snug " + (e.level === "error" || e.level === "critical" ? "font-semibold text-brand-800" :
                    e.kind === "decision" ? "text-ink-soft" : "text-ink")}>{e.message}</p>
                  <p className="mt-0.5 text-[11px] text-ink-faint">{dateTime(e.at)} · {e.kind}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
        {more && events && events.length > 0 && (
          <div className="mt-3 flex justify-center">
            <button className="btn-outline" onClick={loadMore} disabled={loadingMore}>{loadingMore && <Spinner />}Load older</button>
          </div>
        )}
      </div>
    </Sheet>
  );
}
