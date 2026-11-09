import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { IconEye, IconEyeOff, IconX } from "./Icons";
import type { BotStatus } from "../lib/types";

/* ---------- Sheet: a bottom sheet on phones, a centered dialog on larger screens ---------- */
export function Sheet({ title, subtitle, onClose, children, footer, wide = false }: {
  title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-brand-900/40 backdrop-blur-[2px]" onClick={onClose} />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className={"relative flex max-h-[92vh] w-full flex-col rounded-t-3xl bg-white shadow-sheet outline-none sm:rounded-3xl " +
          (wide ? "sm:max-w-2xl" : "sm:max-w-lg")}>
        <div className="flex items-start justify-between gap-3 border-b border-brand-100 px-5 pb-3 pt-4 sm:px-6">
          <div className="min-w-0">
            <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-brand-200 sm:hidden" />
            <h2 id={titleId} className="text-lg font-bold text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-sm text-ink-soft">{subtitle}</p>}
          </div>
          <button className="icon-btn -mr-2 mt-1" onClick={onClose} aria-label="Close"><IconX /></button>
        </div>
        <div className="overflow-y-auto px-5 py-4 sm:px-6">{children}</div>
        {footer && <div className="pb-safe border-t border-brand-100 px-5 py-3 sm:px-6">{footer}</div>}
      </div>
    </div>
  );
}

/* ---------- Confirm ---------- */
export function Confirm({ title, body, confirm, danger = false, busy = false, onConfirm, onCancel, children }: {
  title: string; body: React.ReactNode; confirm: string; danger?: boolean; busy?: boolean;
  onConfirm: () => void; onCancel: () => void; children?: React.ReactNode;
}) {
  return (
    <Sheet title={title} onClose={onCancel} footer={
      <div className="flex justify-end gap-2">
        <button className="btn-ghost" onClick={onCancel}>Cancel</button>
        <button className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirm} disabled={busy}>{confirm}</button>
      </div>}>
      <div className="text-[15px] text-ink-soft">{body}</div>
      {children}
    </Sheet>
  );
}

/* ---------- Field wrapper ---------- */
export function Field({ label, hint, error, children, htmlFor }: {
  label: string; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-semibold text-ink">{label}</label>
      {children}
      {error ? <p className="text-xs font-medium text-brand-700">{error}</p> :
        hint ? <p className="text-xs text-ink-faint">{hint}</p> : null}
    </div>
  );
}

/* ---------- Password input: the eye only reveals what is typed here, never a saved password ---------- */
export function PasswordInput({ id, value, onChange, placeholder, autoComplete = "current-password", required }: {
  id?: string; value: string; onChange: (v: string) => void; placeholder?: string; autoComplete?: string;
  required?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input id={id} className="input pr-11" type={show ? "text" : "password"} value={value} required={required}
        onChange={(e) => onChange(e.target.value)} placeholder={placeholder} autoComplete={autoComplete}
        spellCheck={false} autoCapitalize="off" />
      <button type="button" className="icon-btn absolute right-1 top-1/2 -translate-y-1/2" disabled={!value}
        onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
        aria-pressed={show}>
        {show ? <IconEyeOff /> : <IconEye />}
      </button>
    </div>
  );
}

/* ---------- Segmented control ---------- */
export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; disabled?: boolean; hint?: string }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid auto-cols-fr grid-flow-col gap-1 rounded-xl bg-brand-50 p-1">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} disabled={o.disabled}
          title={o.hint} onClick={() => onChange(o.value)}
          className={"rounded-lg px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
            (value === o.value ? "bg-brand-600 text-white shadow-sm" : "text-ink-soft hover:bg-white/70 hover:text-brand-700")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Status pill ---------- */
const PILL: Record<BotStatus, { label: string; dot: string; cls: string }> = {
  stopped: { label: "Bot stopped", dot: "bg-zinc-400", cls: "bg-zinc-100 text-zinc-600" },
  starting: { label: "Starting…", dot: "bg-amber-500 animate-pulse", cls: "bg-amber-50 text-amber-700" },
  running: { label: "Bot running", dot: "bg-emerald-500", cls: "bg-emerald-50 text-emerald-700" },
  stopping: { label: "Stopping…", dot: "bg-amber-500 animate-pulse", cls: "bg-amber-50 text-amber-700" },
  error: { label: "Error", dot: "bg-brand-600", cls: "bg-brand-100 text-brand-800" },
};

export function StatusPill({ status }: { status: BotStatus }) {
  const p = PILL[status];
  return (
    <span className={"inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold " + p.cls}>
      <span className={"h-2 w-2 rounded-full " + p.dot} aria-hidden="true" />
      {p.label}
    </span>
  );
}

/* ---------- Error box ---------- */
export function ErrorBox({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div role="alert" className="rounded-xl border border-brand-200 bg-brand-50 px-3.5 py-2.5 text-sm font-medium text-brand-800">
      {children}
    </div>
  );
}

/* ---------- Toasts ---------- */
type Toast = { id: number; text: string; tone: "ok" | "error" };
const ToastCtx = createContext<(text: string, tone?: "ok" | "error") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 3800);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-6">
        {items.map((t) => (
          <div key={t.id} className={"pointer-events-auto flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold text-white shadow-sheet " +
            (t.tone === "ok" ? "bg-ink" : "bg-brand-700")}>
            <span className={"h-2 w-2 rounded-full " + (t.tone === "ok" ? "bg-emerald-400" : "bg-white")} />
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
