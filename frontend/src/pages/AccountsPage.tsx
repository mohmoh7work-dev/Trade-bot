import { useState } from "react";
import { del } from "../lib/api";
import type { Account } from "../lib/types";
import { useAccounts } from "../lib/useAccounts";
import AccountCard from "../components/AccountCard";
import AccountForm from "../components/AccountForm";
import LogsSheet from "../components/LogsSheet";
import SettingsSheet from "../components/SettingsSheet";
import { IconPlus, IconWallet, Spinner } from "../components/Icons";
import { Confirm, ErrorBox, useToast } from "../components/ui";

type Open = { kind: "add" } | { kind: "edit" | "settings" | "logs" | "delete"; id: number } | null;

export default function AccountsPage() {
  const { accounts, limits, error, upsert, remove } = useAccounts();
  const toast = useToast();
  const [open, setOpen] = useState<Open>(null);
  const [deleting, setDeleting] = useState(false);
  const current = open && open.kind !== "add" ? accounts?.find((a) => a.id === open.id) ?? null : null;

  async function doDelete(a: Account) {
    setDeleting(true);
    try {
      await del("/api/accounts/" + a.id);
      remove(a.id);
      toast("Deleted " + a.nickname);
      setOpen(null);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section aria-labelledby="accounts-h">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="accounts-h" className="text-2xl font-extrabold tracking-tight sm:text-3xl">Broker accounts</h1>
          <p className="mt-1 text-[15px] text-ink-soft">Connect the MT5 account the bot should trade, then start or stop it here.</p>
        </div>
        <button className="btn-primary" onClick={() => setOpen({ kind: "add" })}>
          <IconPlus className="h-4 w-4" />Add account
        </button>
      </div>

      <div className="mt-5">
        <ErrorBox>{error}</ErrorBox>
        {accounts === null ? (
          <div className="flex justify-center py-16 text-brand-700"><Spinner className="h-7 w-7" /></div>
        ) : accounts.length === 0 ? (
          <div className="card flex flex-col items-center px-6 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700"><IconWallet className="h-6 w-6" /></span>
            <h2 className="mt-3 text-lg font-bold">No broker accounts yet</h2>
            <p className="mt-1 max-w-sm text-sm text-ink-soft">Add your MT5 login. mohz bot checks it with your broker, then you can start the bot on it.</p>
            <button className="btn-primary mt-5" onClick={() => setOpen({ kind: "add" })}><IconPlus className="h-4 w-4" />Add account</button>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {accounts.map((a) => (
              <AccountCard key={a.id} account={a} onChange={upsert}
                onEdit={() => setOpen({ kind: "edit", id: a.id })} onDelete={() => setOpen({ kind: "delete", id: a.id })}
                onSettings={() => setOpen({ kind: "settings", id: a.id })} onLogs={() => setOpen({ kind: "logs", id: a.id })} />
            ))}
          </div>
        )}
      </div>

      {open?.kind === "add" && (
        <AccountForm onClose={() => setOpen(null)} onSaved={(a, note) => {
          upsert(a);
          setOpen(null);
          toast(note ?? "Added " + a.nickname);
        }} />
      )}
      {open?.kind === "edit" && current && (
        <AccountForm account={current} onClose={() => setOpen(null)} onSaved={(a, note) => {
          upsert(a);
          setOpen(null);
          toast(note ?? "Saved " + a.nickname);
        }} />
      )}
      {open?.kind === "settings" && current && (
        <SettingsSheet account={current} limits={limits} onClose={() => setOpen(null)} onSaved={(a) => {
          upsert(a);
          setOpen(null);
          toast("Settings saved for " + a.nickname);
        }} />
      )}
      {open?.kind === "logs" && current && <LogsSheet account={current} onClose={() => setOpen(null)} />}
      {open?.kind === "delete" && current && (
        <Confirm title={"Delete " + current.nickname + "?"} confirm="Delete account" danger busy={deleting}
          onCancel={() => setOpen(null)} onConfirm={() => doDelete(current)}
          body={<>This removes the account, its saved password and its activity log from mohz bot.
            {current.bot.desired === "running" && (current.settings.close_on_stop ?
              " The bot is running: it will be stopped and its open trades closed." :
              " The bot is running: it will be stopped and its open trades left as they are.")}</>} />
      )}
    </section>
  );
}
