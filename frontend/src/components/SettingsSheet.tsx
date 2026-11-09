import { useState } from "react";
import { put } from "../lib/api";
import type { Account, BotSettings, Limits } from "../lib/types";
import { IconPlus, IconX, Spinner } from "./Icons";
import { ErrorBox, Field, Segmented, Sheet } from "./ui";

type Props = { account: Account; limits: Limits | null; onSaved: (a: Account) => void; onClose: () => void };

function Num({ id, value, onChange, step, min, max, suffix }: {
  id: string; value: number; onChange: (v: number) => void; step: number; min: number; max?: number; suffix?: string;
}) {
  return (
    <div className="relative">
      <input id={id} className="input pr-12 tabular-nums" type="number" inputMode="decimal" step={step} min={min} max={max}
        value={Number.isNaN(value) ? "" : value} onChange={(e) => onChange(parseFloat(e.target.value))} required />
      {suffix && <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-ink-faint">{suffix}</span>}
    </div>
  );
}

export default function SettingsSheet({ account, limits, onSaved, onClose }: Props) {
  const [s, setS] = useState<BotSettings>(structuredClone(account.settings));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof BotSettings>(k: K, v: BotSettings[K]) => setS((x) => ({ ...x, [k]: v }));
  const lim = limits ?? { risk_pct: 2, lot: 2, max_open_trades: 3, daily_loss_pct: 6, max_drawdown_pct: 20 };

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await put<{ account: Account }>("/api/accounts/" + account.id + "/settings", s);
      onSaved(r.account);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title="Bot settings" subtitle={account.nickname + (account.bot.desired === "running" ?
      " · changes reach the running bot within a few seconds" : "")} onClose={onClose}
      footer={<div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
        <button form="settings-form" className="btn-primary" disabled={busy}>{busy && <Spinner />}Save settings</button>
      </div>}>
      <form id="settings-form" onSubmit={save} className="space-y-5">
        <section className="space-y-3">
          <h3 className="field-label">Trade size</h3>
          <Segmented label="Trade size" value={s.sizing} onChange={(v) => set("sizing", v)}
            options={[{ value: "risk", label: "% risk per trade" }, { value: "lot", label: "Fixed lot size" }]} />
          {s.sizing === "risk" ? (
            <Field label="Risk per trade" htmlFor="s-risk" hint={"Share of the balance lost if the stop is hit. Max " + lim.risk_pct + "%."}>
              <Num id="s-risk" value={s.risk_pct} onChange={(v) => set("risk_pct", v)} step={0.05} min={0.01} max={lim.risk_pct} suffix="%" />
            </Field>
          ) : (
            <Field label="Lot size" htmlFor="s-lot" hint={"1.00 lot = 100 oz of gold. Max " + lim.lot + "."}>
              <Num id="s-lot" value={s.lot} onChange={(v) => set("lot", v)} step={0.01} min={0.01} max={lim.lot} suffix="lot" />
            </Field>
          )}
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <Field label="Max open trades" htmlFor="s-open" hint={"At most " + lim.max_open_trades + "."}>
            <Num id="s-open" value={s.max_open_trades} onChange={(v) => set("max_open_trades", Math.round(v))} step={1} min={1} max={lim.max_open_trades} />
          </Field>
          <Field label="Max spread" htmlFor="s-spread" hint="No new trade when the spread is wider (in $).">
            <Num id="s-spread" value={s.max_spread} onChange={(v) => set("max_spread", v)} step={0.05} min={0.01} suffix="$" />
          </Field>
          <Field label="Daily loss limit" htmlFor="s-daily" hint="Reached: the bot closes its trades and stops.">
            <Num id="s-daily" value={s.daily_loss_pct} onChange={(v) => set("daily_loss_pct", v)} step={0.5} min={0.1} max={lim.daily_loss_pct} suffix="%" />
          </Field>
          <Field label="Max drawdown" htmlFor="s-dd" hint="From the equity peak. Reached: close all and stop.">
            <Num id="s-dd" value={s.max_drawdown_pct} onChange={(v) => set("max_drawdown_pct", v)} step={0.5} min={0.5} max={lim.max_drawdown_pct} suffix="%" />
          </Field>
        </section>

        <section className="space-y-2">
          <h3 className="field-label">Trading hours (New York time)</h3>
          {s.trading_hours.length === 0 && (
            <p className="text-sm text-ink-soft">Default: the London and New York sessions (03:00–17:00 New York).</p>
          )}
          {s.trading_hours.map((w, i) => (
            <div key={i} className="flex items-center gap-2">
              <input type="time" className="input" value={w.from} aria-label="From" required
                onChange={(e) => set("trading_hours", s.trading_hours.map((x, j) => (j === i ? { ...x, from: e.target.value } : x)))} />
              <span className="text-ink-faint">to</span>
              <input type="time" className="input" value={w.to} aria-label="To" required
                onChange={(e) => set("trading_hours", s.trading_hours.map((x, j) => (j === i ? { ...x, to: e.target.value } : x)))} />
              <button type="button" className="icon-btn shrink-0" aria-label="Remove window"
                onClick={() => set("trading_hours", s.trading_hours.filter((_, j) => j !== i))}><IconX /></button>
            </div>
          ))}
          {s.trading_hours.length < 6 && (
            <button type="button" className="btn-ghost -ml-2 px-2 py-1.5 text-sm"
              onClick={() => set("trading_hours", [...s.trading_hours, { from: "08:30", to: "12:00" }])}>
              <IconPlus className="h-4 w-4" />Add a trading window
            </button>
          )}
        </section>

        <section className="space-y-2">
          <h3 className="field-label">When I press Stop bot</h3>
          {([[true, "Close the bot's open trades", "Positions the bot opened are closed at the market price."],
            [false, "Leave open trades as they are", "Their stop loss and take-profit stay at the broker."]] as const).map(([v, t, d]) => (
            <label key={String(v)} className={"flex cursor-pointer items-start gap-3 rounded-xl border p-3 " +
              (s.close_on_stop === v ? "border-brand-400 bg-brand-50" : "border-brand-100")}>
              <input type="radio" name="close_on_stop" className="mt-1 accent-brand-600" checked={s.close_on_stop === v}
                onChange={() => set("close_on_stop", v)} />
              <span><span className="block text-sm font-semibold">{t}</span><span className="block text-xs text-ink-faint">{d}</span></span>
            </label>
          ))}
        </section>
        <ErrorBox>{error}</ErrorBox>
      </form>
    </Sheet>
  );
}
