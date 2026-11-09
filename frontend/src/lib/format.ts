export function money(v: number | null | undefined, currency?: string | null, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const abs = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sign = v < 0 ? "−" : signed && v > 0 ? "+" : "";
  const cur = currency && currency !== "USD" ? " " + currency : "";
  const sym = !currency || currency === "USD" ? "$" : "";
  return sign + sym + abs + cur;
}

export function price(v: number | null | undefined): string {
  return v === null || v === undefined ? "–" : v.toFixed(2);
}

export function time(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

export function secondsUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000));
}

export function duration(s: number): string {
  if (s < 60) return s + " s";
  const m = Math.round(s / 60);
  return m < 60 ? m + " min" : Math.round(m / 60) + " h";
}
