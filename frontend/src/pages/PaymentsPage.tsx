import { useEffect, useState } from "react";
import { get } from "../lib/api";
import { date, money } from "../lib/format";
import type { Payment } from "../lib/types";
import { IconReceipt, Spinner } from "../components/Icons";
import { ErrorBox } from "../components/ui";

const STATUS: Record<string, string> = {
  paid: "bg-emerald-50 text-emerald-700", pending: "bg-amber-50 text-amber-700",
  failed: "bg-brand-100 text-brand-800", refunded: "bg-zinc-100 text-zinc-600",
};

export default function PaymentsPage() {
  const [rows, setRows] = useState<Payment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<{ payments: Payment[] }>("/api/payments").then((r) => setRows(r.payments)).catch((e) => setError(e.message));
  }, []);
  const amount = (p: Payment) => money(p.amount_cents / 100, p.currency);
  const badge = (s: string) => (
    <span className={"rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize " + (STATUS[s] ?? STATUS.refunded)}>{s}</span>
  );
  const invoice = (p: Payment) => p.invoice_url ?
    <a href={p.invoice_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-brand-700 hover:underline">Invoice</a> :
    <span className="text-ink-faint">–</span>;

  return (
    <section aria-labelledby="pay-h">
      <h1 id="pay-h" className="text-2xl font-extrabold tracking-tight sm:text-3xl">Payment history</h1>
      <p className="mt-1 text-[15px] text-ink-soft">Your mohz bot payments and invoices.</p>
      <div className="mt-5">
        <ErrorBox>{error}</ErrorBox>
        {rows === null && !error ? (
          <div className="flex justify-center py-16 text-brand-700"><Spinner className="h-7 w-7" /></div>
        ) : rows && rows.length === 0 ? (
          <div className="card flex flex-col items-center px-6 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700"><IconReceipt className="h-6 w-6" /></span>
            <p className="mt-3 font-semibold">No payments recorded yet.</p>
          </div>
        ) : rows ? (
          <div className="card overflow-hidden">
            <table className="hidden w-full text-left text-sm sm:table">
              <thead className="bg-brand-50 text-xs uppercase tracking-wider text-ink-faint">
                <tr><th className="px-5 py-3">Date</th><th className="px-5 py-3">Amount</th><th className="px-5 py-3">Plan</th>
                  <th className="px-5 py-3">Status</th><th className="px-5 py-3">Invoice</th></tr>
              </thead>
              <tbody className="divide-y divide-brand-100">
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td className="px-5 py-3">{date(p.date)}</td>
                    <td className="px-5 py-3 font-semibold tabular-nums">{amount(p)}</td>
                    <td className="px-5 py-3">{p.plan ?? "–"}</td>
                    <td className="px-5 py-3">{badge(p.status)}</td>
                    <td className="px-5 py-3">{invoice(p)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-brand-100 sm:hidden">
              {rows.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                  <div>
                    <p className="font-semibold tabular-nums">{amount(p)} <span className="font-normal text-ink-soft">· {p.plan ?? "–"}</span></p>
                    <p className="text-xs text-ink-faint">{date(p.date)}</p>
                  </div>
                  <div className="flex items-center gap-3">{badge(p.status)}{invoice(p)}</div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
