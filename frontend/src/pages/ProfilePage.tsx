import { useState } from "react";
import { del, patch, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date } from "../lib/format";
import type { User } from "../lib/types";
import { IconLink, IconLogout, Spinner } from "../components/Icons";
import { Confirm, ErrorBox, Field, PasswordInput, useToast } from "../components/ui";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="text-base font-bold">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export default function ProfilePage() {
  const { user, setUser, logout } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user!.name);
  const [savingName, setSavingName] = useState(false);
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwBusy, setPwBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [delPw, setDelPw] = useState("");
  const [delError, setDelError] = useState<string | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const u = user!;

  async function saveName(e: React.FormEvent) {
    e.preventDefault();
    setSavingName(true);
    try {
      const r = await patch<{ user: User }>("/api/me", { name });
      setUser(r.user);
      toast("Name saved");
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setSavingName(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwError(null);
    setPwBusy(true);
    try {
      await post("/api/me/password", { current_password: cur, new_password: next });
      setCur("");
      setNext("");
      toast("Password changed. Other devices were logged out.");
    } catch (err) {
      setPwError((err as Error).message);
    } finally {
      setPwBusy(false);
    }
  }

  async function telegram() {
    try {
      if (u.telegram.connected) {
        const r = await del<{ user: User }>("/api/me/telegram");
        setUser(r.user);
        toast("Telegram disconnected");
      } else {
        const r = await post<{ url: string }>("/api/me/telegram");
        window.open(r.url, "_blank", "noopener");
      }
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  async function deleteAccount() {
    setDelError(null);
    setDelBusy(true);
    try {
      await del("/api/me", { password: delPw });
      setUser(null);
    } catch (err) {
      setDelError((err as Error).message);
      setDelBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Account details</h1>
        <p className="mt-1 text-[15px] text-ink-soft">Member since {date(u.created_at)}.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile">
          <form onSubmit={saveName} className="space-y-3">
            <Field label="Name" htmlFor="p-name">
              <input id="p-name" className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
            </Field>
            <Field label="Email" htmlFor="p-email">
              <input id="p-email" className="input" value={u.email} disabled readOnly />
            </Field>
            <button className="btn-outline" disabled={savingName || name.trim() === u.name}>{savingName && <Spinner />}Save name</button>
          </form>
        </Card>

        <Card title="Plan">
          <p className="text-sm text-ink-soft">Current plan</p>
          <p className="mt-0.5 text-xl font-extrabold text-brand-700">{u.plan?.name ?? "Free"}</p>
          <p className="mt-3 text-sm text-ink-faint">Billing is coming soon. Your payments will show under Payment history.</p>
        </Card>

        <Card title="Change password">
          <form onSubmit={changePassword} className="space-y-3">
            <Field label="Current password" htmlFor="p-cur">
              <PasswordInput id="p-cur" value={cur} onChange={setCur} required />
            </Field>
            <Field label="New password" htmlFor="p-new" hint="At least 10 characters.">
              <PasswordInput id="p-new" value={next} onChange={setNext} required autoComplete="new-password" />
            </Field>
            <ErrorBox>{pwError}</ErrorBox>
            <button className="btn-outline" disabled={pwBusy || !cur || !next}>{pwBusy && <Spinner />}Change password</button>
          </form>
        </Card>

        <Card title="Alerts">
          <p className="text-sm text-ink-soft">Get every signal, trade and error from your bots in Telegram.</p>
          {u.telegram.available ? (
            <button className="btn-outline mt-3" onClick={telegram}>
              <IconLink className="h-4 w-4" />{u.telegram.connected ? "Disconnect Telegram" : "Connect Telegram"}
            </button>
          ) : (
            <p className="mt-3 text-sm text-ink-faint">Telegram alerts are not set up on this server yet.</p>
          )}
          {u.telegram.connected && <p className="mt-2 text-sm font-semibold text-emerald-700">Connected</p>}
        </Card>
      </div>

      <section className="card flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="text-base font-bold">Log out</h2>
          <p className="text-sm text-ink-soft">Your bots keep running after you log out.</p>
        </div>
        <button className="btn-outline" onClick={logout}><IconLogout className="h-4 w-4" />Log out</button>
      </section>

      <section className="card border-brand-200 p-5">
        <h2 className="text-base font-bold text-brand-800">Delete account</h2>
        <p className="mt-1 text-sm text-ink-soft">Stops every bot, deletes your broker accounts, saved passwords and history. This cannot be undone.</p>
        <button className="btn-danger mt-3" onClick={() => setAskDelete(true)}>Delete my account</button>
      </section>

      {askDelete && (
        <Confirm title="Delete your mohz bot account?" confirm="Delete forever" danger busy={delBusy || !delPw}
          onCancel={() => { setAskDelete(false); setDelPw(""); setDelError(null); }} onConfirm={deleteAccount}
          body="Every bot is stopped (closing trades where the account's settings say so) and all your data is deleted.">
          <div className="mt-4 space-y-3">
            <Field label="Your password" htmlFor="d-pw"><PasswordInput id="d-pw" value={delPw} onChange={setDelPw} /></Field>
            <ErrorBox>{delError}</ErrorBox>
          </div>
        </Confirm>
      )}
    </div>
  );
}
