import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { User } from "../lib/types";
import { ErrorBox, Field, PasswordInput } from "../components/ui";
import { Spinner } from "../components/Icons";
import { Wordmark } from "../components/Wordmark";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const register = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await post<{ user: User }>(register ? "/api/auth/register" : "/api/auth/login",
        register ? { name, email, password } : { email, password });
      setUser(r.user);
      nav("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6 text-center">
        <Wordmark className="text-4xl" />
        <p className="mt-2 text-[15px] text-ink-soft">Run the XAUUSD council bot on your MT5 accounts.</p>
      </div>
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <h1 className="text-xl font-bold">{register ? "Create your account" : "Log in"}</h1>
        {register && (
          <Field label="Name" htmlFor="name">
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} required
              autoComplete="name" maxLength={120} />
          </Field>
        )}
        <Field label="Email" htmlFor="email">
          <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            required autoComplete="email" inputMode="email" />
        </Field>
        <Field label="Password" htmlFor="password" hint={register ? "At least 10 characters." : undefined}>
          <PasswordInput id="password" value={password} onChange={setPassword} required
            autoComplete={register ? "new-password" : "current-password"} />
        </Field>
        <ErrorBox>{error}</ErrorBox>
        <button className="btn-primary w-full" disabled={busy}>
          {busy && <Spinner />}{register ? "Create account" : "Log in"}
        </button>
        <p className="text-center text-sm text-ink-soft">
          {register ? "Already have an account? " : "New to mohz bot? "}
          <Link to={register ? "/login" : "/register"} className="font-semibold text-brand-700 hover:underline">
            {register ? "Log in" : "Create an account"}
          </Link>
        </p>
      </form>
      <p className="mt-6 max-w-sm text-center text-xs text-ink-faint">
        Trading gold CFDs is risky and most traders lose money. The bot can lose money too.
      </p>
    </div>
  );
}
