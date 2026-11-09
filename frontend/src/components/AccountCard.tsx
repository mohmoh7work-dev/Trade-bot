import { useState } from "react";
import { post } from "../lib/api";
import { duration, money, price, secondsUntil, time } from "../lib/format";
import type { Account } from "../lib/types";
import { useTicker } from "../lib/useAccounts";
import { IconList, IconPencil, IconPlay, IconSliders, IconStop, IconTrash, Spinner } from "./Icons";
import { Confirm, StatusPill, useToast } from "./ui";

type Props = {
  account: Account;
  onChange: (a: Account) => void;
  onEdit: () => void;
  onDelete: () => void;
  onSettings: () => void;
  onLogs: () => void;
};

function statusLine(a: Account): { text: string; tone: "muted" | "ok" | "warn" | "error" } {
  const b = a.bot;
  const what = a.mode === "auto" ? "auto-trading " + a.symbol : "sending " + a.symbol + " alerts only (no orders)";
  switch (b.status) {
    case "running": {
      if (a.live && a.live.market_open === false) {
        return { text: "Bot is running on this account. Gold market is closed, so it is waiting.", tone: "ok" };
      }
      const since = b.started_at ? " since " + time(b.started_at) : "";
      return { text: "Bot is running on this account" + since + ", " + what + ".", tone: "ok" };
    }
    case "starting":
      return { text: "Logging in to the broker and starting the bot…", tone: "warn" };
    case "stopping":
      return {
        text: a.settings.close_on_stop ? "Stopping the bot and closing its open trades…" : "Stopping the bot…",
        tone: "warn",
      };
    case "error": {
      const s = secondsUntil(b.retry_at);
      const retry = s !== null ? (s > 0 ? " Retrying in " + duration(s) + "." : " Retrying now…") : "";
      return { text: (b.reason || "The bot hit a problem.") + retry, tone: "error" };
    }
    default:
      return { text: b.reason || "Bot is idle on this account.", tone: b.reason ? "warn" : "muted" };
  }
}

const TONE = {
  muted: "text-ink-faint",
  ok: "text-emerald-700",
  warn: "text-amber-700",
  error: "text-brand-700",
};

export default function AccountCard({ account: a, onChange, onEdit, onDelete, onSettings, onLogs }: Props) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const wantsRunning = a.bot.desired === "running";
  const transitioning = a.bot.status === "starting" || a.bot.status === "stopping";
  useTicker(a.bot.status === "error" && !!a.bot.retry_at);
  const line = statusLine(a);
  const positions = a.live?.positions ?? [];

  async function run(action: "start" | "stop") {
    setBusy(true);
    try {
      const r = await post<{ account: Account }>("/api/accounts/" + a.id + "/" + action);
      onChange(r.account);
      toast((action === "start" ? "Bot started for " : "Bot stopped for ") + a.nickname);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
      setConfirmStop(false);
    }
  }

  function onToggle() {
    if (!wantsRunning) return run("start");
    if (a.settings.close_on_stop && positions.length > 0) return setConfirmStop(true);
    return run("stop");
  }

  const pnl = a.live?.today_pnl ?? null;
  return (
    <article className="card flex flex-col p-4 sm:p-5" aria-label={a.nickname}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-[17px] font-bold text-ink">{a.nickname}</h3>
            <span className="rounded-md bg-ink px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-white">{a.platform}</span>
          </div>
          <p className="mt-0.5 truncate text-sm text-ink-soft">{a.broker} · {a.server}</p>
        </div>
        <StatusPill status={a.bot.status} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="chip">{a.symbol}</span>
        <span className="chip">{a.mode === "auto" ? "Auto-trade" : "Alerts only"}</span>
        {a.account_type === "real" ? <span className="chip bg-ink text-white">Real money</span> :
          <span className="chip bg-white ring-1 ring-brand-200">Demo</span>}
        <div className="ml-auto flex items-center">
          <button className="icon-btn" onClick={onLogs} aria-label={"Activity log for " + a.nickname} title="Activity log"><IconList /></button>
          <button className="icon-btn" onClick={onSettings} aria-label={"Bot settings for " + a.nickname} title="Bot settings"><IconSliders /></button>
          <button className="icon-btn" onClick={onEdit} aria-label={"Edit " + a.nickname} title="Edit"><IconPencil /></button>
          <button className="icon-btn hover:text-brand-700" onClick={onDelete} aria-label={"Delete " + a.nickname} title="Delete"><IconTrash /></button>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 rounded-xl bg-brand-50/70 p-3">
        <div className="min-w-0">
          <dt className="field-label">Server</dt>
          <dd className="mt-0.5 truncate text-sm font-semibold" title={a.server}>{a.server}</dd>
        </div>
        <div className="min-w-0">
          <dt className="field-label">Login</dt>
          <dd className="mt-0.5 truncate text-sm font-semibold tabular-nums">{a.login}</dd>
        </div>
        <div className="min-w-0">
          <dt className="field-label">Password</dt>
          <dd className="mt-0.5 text-sm font-semibold tracking-[0.2em]" aria-label="Password hidden">
            {a.password_set ? "••••••••" : "not set"}
          </dd>
        </div>
      </dl>

      {a.live && wantsRunning && (
        <div className="mt-3 space-y-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Balance" value={money(a.live.balance, a.currency)} />
            <Stat label="Equity" value={money(a.live.equity, a.currency)} />
            <Stat label="Today's P/L" value={money(pnl, a.currency, true)}
              tone={pnl === null ? undefined : pnl >= 0 ? "text-emerald-700" : "text-brand-700"} />
            <Stat label="Open positions" value={String(positions.length)} />
          </div>
          {positions.length > 0 && (
            <ul className="divide-y divide-brand-100 rounded-xl border border-brand-100">
              {positions.map((p) => (
                <li key={p.ticket} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="flex items-center gap-2">
                    <span className={"rounded-md px-1.5 py-0.5 text-[11px] font-bold " +
                      (p.side === "BUY" ? "bg-emerald-50 text-emerald-700" : "bg-brand-100 text-brand-800")}>{p.side}</span>
                    <span className="tabular-nums">{p.lots.toFixed(2)} @ {price(p.open_price)}</span>
                    <span className="hidden text-xs text-ink-faint sm:inline">SL {price(p.sl)} · TP {price(p.tp)}</span>
                  </span>
                  <span className={"font-semibold tabular-nums " + ((p.profit ?? 0) >= 0 ? "text-emerald-700" : "text-brand-700")}>
                    {money(p.profit, a.currency, true)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {a.live.bid !== null && (
            <p className="text-xs text-ink-faint tabular-nums">
              {a.symbol} bid {price(a.live.bid)} · ask {price(a.live.ask)} · updated {time(a.live.at)}
            </p>
          )}
        </div>
      )}

      <div className="mt-auto pt-4">
        <button onClick={onToggle} disabled={busy || transitioning}
          className={"w-full " + (wantsRunning ? "btn-outline" : "btn-primary")}>
          {busy || transitioning ? <Spinner /> : wantsRunning ? <IconStop className="h-4 w-4" /> : <IconPlay className="h-4 w-4" />}
          {a.bot.status === "starting" ? "Starting…" : a.bot.status === "stopping" ? "Stopping…" :
            wantsRunning ? "Stop bot" : "Start bot"}
        </button>
        <p className={"mt-2 text-[13px] leading-snug " + TONE[line.tone]} role="status">{line.text}</p>
      </div>

      {confirmStop && (
        <Confirm title={"Stop the bot on " + a.nickname + "?"} confirm="Stop and close trades" busy={busy}
          onConfirm={() => run("stop")} onCancel={() => setConfirmStop(false)}
          body={<>The bot has {positions.length} open position{positions.length === 1 ? "" : "s"}. Stopping closes
            {positions.length === 1 ? " it" : " them"} at the market price. You can change this in Bot settings.</>} />
      )}
    </article>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-brand-100 bg-white px-3 py-2">
      <div className="field-label">{label}</div>
      <div className={"mt-0.5 text-[15px] font-bold tabular-nums " + (tone ?? "text-ink")}>{value}</div>
    </div>
  );
}
