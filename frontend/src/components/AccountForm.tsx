import { useState } from "react";
import { ApiError, patch, post } from "../lib/api";
import { money } from "../lib/format";
import type { Account, DetectResult } from "../lib/types";
import { IconAlert, IconSearch, Spinner } from "./Icons";
import { ErrorBox, Field, PasswordInput, Segmented, Sheet } from "./ui";

type Props = { account?: Account; onSaved: (a: Account, note?: string) => void; onClose: () => void };

export default function AccountForm({ account, onSaved, onClose }: Props) {
  const editing = !!account;
  const running = !!account && account.bot.desired === "running";
  const [nickname, setNickname] = useState(account?.nickname ?? "");
  const [broker, setBroker] = useState(account?.broker ?? "");
  const [server, setServer] = useState(account?.server ?? "");
  const [login, setLogin] = useState(account?.login ?? "");
  const [password, setPassword] = useState("");          // never prefilled: saved passwords stay on the server
  const [symbol, setSymbol] = useState(account?.symbol ?? "XAUUSD");
  const [mode, setMode] = useState<"auto" | "alerts">(account?.mode ?? "alerts");
  const [allowLive, setAllowLive] = useState(account?.allow_live ?? false);
  const [confirmText, setConfirmText] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detected, setDetected] = useState<DetectResult | null>(null);
  const turningLiveOn = allowLive && !account?.allow_live;

  async function detect() {
    setError(null);
    if (!server.trim() || !login.trim() || (!password && !editing)) {
      setError("Enter the server, login and password first, then tap Detect.");
      return;
    }
    setDetecting(true);
    try {
      const r = await post<DetectResult>("/api/accounts/detect", {
        server, login, password: password || null, symbol, account_id: editing && !password ? account!.id : null,
      });
      setDetected(r);
      if (r.symbol) setSymbol(r.symbol);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDetecting(false);
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const live = turningLiveOn ? { confirm_text: confirmText, confirm_password: confirmPassword } : {};
    try {
      let r: { account: Account; probe: DetectResult | null };
      if (!editing) {
        r = await post("/api/accounts", { nickname, platform: "MT5", broker, server, login, password, symbol, mode,
          allow_live: allowLive, ...live });
      } else {
        const body: Record<string, unknown> = {};
        const cur = account!;
        if (nickname !== cur.nickname) body.nickname = nickname;
        if (broker !== cur.broker) body.broker = broker;
        if (server !== cur.server) body.server = server;
        if (login !== cur.login) body.login = login;
        if (symbol !== cur.symbol) body.symbol = symbol;
        if (mode !== cur.mode) body.mode = mode;
        if (allowLive !== cur.allow_live) body.allow_live = allowLive;
        if (password) body.password = password;
        if (Object.keys(body).length === 0) return onClose();
        r = await patch("/api/accounts/" + cur.id, { ...body, ...live });
      }
      const p = r.probe;
      const note = p && p.symbol && p.symbol_exact === false ? "This account calls gold " + p.symbol + ": using that." : undefined;
      onSaved(r.account, note);
    } catch (err) {
      const ex = err as ApiError;
      if (ex.code === "real_account") setAllowLive(true);
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  const lockLogin = running;
  return (
    <Sheet title={editing ? "Edit " + account!.nickname : "Add broker account"}
      subtitle={editing ? undefined : "mohz bot logs in to check these details before saving."}
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-ink-faint">{busy ? "Checking the login with your broker. This can take up to a minute." : ""}</p>
          <div className="flex shrink-0 gap-2">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button form="account-form" className="btn-primary" disabled={busy}>
              {busy && <Spinner />}{busy ? "Checking…" : "Save"}
            </button>
          </div>
        </div>
      }>
      <form id="account-form" onSubmit={save} className="space-y-4" autoComplete="off">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nickname" htmlFor="f-nick">
            <input id="f-nick" className="input" value={nickname} onChange={(e) => setNickname(e.target.value)}
              placeholder="My gold account" required maxLength={60} />
          </Field>
          <Field label="Platform" htmlFor="f-platform" hint="Only MetaTrader 5 is supported.">
            <input id="f-platform" className="input" value="MT5" disabled readOnly />
          </Field>
        </div>
        {lockLogin && (
          <p className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
            Stop the bot to change the server, login, password, symbol or real-money setting.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Broker" htmlFor="f-broker">
            <input id="f-broker" className="input" value={broker} onChange={(e) => setBroker(e.target.value)}
              placeholder="e.g. JustMarkets" required maxLength={80} />
          </Field>
          <Field label="Server" htmlFor="f-server" hint="Exactly as MT5 shows it, e.g. JustMarkets-Demo.">
            <input id="f-server" className="input" value={server} onChange={(e) => setServer(e.target.value)}
              required maxLength={120} disabled={lockLogin} autoCapitalize="off" spellCheck={false} />
          </Field>
          <Field label="Login" htmlFor="f-login">
            <input id="f-login" className="input tabular-nums" value={login} inputMode="numeric" pattern="[0-9]*"
              onChange={(e) => setLogin(e.target.value.replace(/\D/g, ""))} required maxLength={20} disabled={lockLogin}
              autoComplete="off" />
          </Field>
          <Field label="Password" htmlFor="f-password"
            hint={editing ? "Leave empty to keep the saved password." : "The trading (master) password, not the investor one."}>
            {lockLogin ? <input className="input" value="••••••••" disabled readOnly /> :
              <PasswordInput id="f-password" value={password} onChange={setPassword} required={!editing}
                autoComplete="new-password" placeholder={editing ? "••••••••  (saved)" : ""} />}
          </Field>
        </div>

        <Field label="Symbol" htmlFor="f-symbol"
          hint={detected ? undefined : "Brokers name gold differently (XAUUSDm, XAUUSD.m…). Detect finds it."}>
          <div className="flex gap-2">
            <input id="f-symbol" className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)}
              required maxLength={32} disabled={lockLogin} autoCapitalize="characters" spellCheck={false} />
            <button type="button" className="btn-outline shrink-0" onClick={detect} disabled={detecting || lockLogin}>
              {detecting ? <Spinner /> : <IconSearch className="h-4 w-4" />}Detect
            </button>
          </div>
        </Field>
        {detected && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-900">
            <p className="font-semibold">Logged in{detected.company ? " at " + detected.company : ""}: {detected.type ?? "?"} account
              {detected.balance !== null ? ", balance " + money(detected.balance, detected.currency) : ""}.</p>
            <p className="mt-1">Gold on this account: <b>{detected.symbol}</b></p>
            {detected.symbols.length > 1 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {detected.symbols.map((s) => (
                  <button key={s} type="button" onClick={() => setSymbol(s)}
                    className={"rounded-full px-2.5 py-0.5 text-xs font-semibold " +
                      (s === symbol ? "bg-emerald-700 text-white" : "bg-white text-emerald-800 ring-1 ring-emerald-200")}>
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <Field label="Mode" hint={mode === "auto" ? "The bot opens and closes trades by itself." :
          "The bot analyses and sends you each signal. It never places an order."}>
          <Segmented label="Mode" value={mode} onChange={setMode}
            options={[{ value: "auto", label: "Auto-trade" }, { value: "alerts", label: "Alerts only" }]} />
        </Field>

        <div className="rounded-xl border border-brand-100 p-3.5">
          <label className="flex cursor-pointer items-start gap-3">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-600" checked={allowLive}
              onChange={(e) => setAllowLive(e.target.checked)} disabled={lockLogin} />
            <span>
              <span className="block text-sm font-semibold">Allow real money</span>
              <span className="block text-xs text-ink-faint">Off: the bot only runs on demo accounts. Start on demo first.</span>
            </span>
          </label>
          {turningLiveOn && (
            <div className="mt-3 space-y-3 border-t border-brand-100 pt-3">
              <p className="text-sm text-brand-800">The bot will trade real money on this account and can lose it.
                Type <b>LIVE</b> and your mohz bot password to confirm.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <input className="input" value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="Type LIVE" aria-label="Type LIVE to confirm" autoCapitalize="characters" />
                <PasswordInput value={confirmPassword} onChange={setConfirmPassword} placeholder="Your mohz bot password"
                  autoComplete="current-password" />
              </div>
            </div>
          )}
        </div>
        <ErrorBox>{error}</ErrorBox>
      </form>
    </Sheet>
  );
}
