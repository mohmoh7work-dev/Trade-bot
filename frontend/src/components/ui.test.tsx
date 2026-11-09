import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { PasswordInput, StatusPill } from "./ui";
import AccountCard from "./AccountCard";
import type { Account } from "../lib/types";

function Pw() {
  const [v, setV] = useState("");
  return <PasswordInput id="pw" value={v} onChange={setV} />;
}

describe("PasswordInput", () => {
  it("the eye only reveals what was typed", () => {
    render(<Pw />);
    const input = document.getElementById("pw") as HTMLInputElement;
    const eye = screen.getByRole("button", { name: "Show password" });
    expect(eye).toBeDisabled();              // nothing typed: nothing to reveal
    fireEvent.change(input, { target: { value: "s3cret" } });
    expect(input.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input.type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(input.type).toBe("password");
  });
});

describe("StatusPill", () => {
  it("labels", () => {
    render(<><StatusPill status="stopped" /><StatusPill status="running" /><StatusPill status="error" /></>);
    expect(screen.getByText("Bot stopped")).toBeInTheDocument();
    expect(screen.getByText("Bot running")).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
  });
});

const base: Account = {
  id: 1, nickname: "Gold demo", platform: "MT5", broker: "JustMarkets", server: "JustMarkets-Demo",
  login: "12345", symbol: "XAUUSD.m", mode: "auto", allow_live: false, account_type: "demo", currency: "USD",
  password_set: true,
  settings: { sizing: "risk", risk_pct: 0.5, lot: 0.01, max_open_trades: 1, max_spread: 0.6, daily_loss_pct: 3,
    max_drawdown_pct: 10, trading_hours: [], close_on_stop: true },
  bot: { status: "stopped", desired: "stopped", reason: null, retry_at: null, started_at: null, heartbeat_at: null },
  live: null, last_event_id: null, created_at: "2026-11-09T10:00:00Z",
};

const noop = vi.fn();
const card = (a: Account) => render(<AccountCard account={a} onChange={noop} onEdit={noop} onDelete={noop}
  onSettings={noop} onLogs={noop} />);

describe("AccountCard", () => {
  it("shows the account with the password masked and an idle line", () => {
    card(base);
    expect(screen.getByText("Gold demo")).toBeInTheDocument();
    expect(screen.getByText("JustMarkets · JustMarkets-Demo")).toBeInTheDocument();
    expect(screen.getByLabelText("Password hidden")).toHaveTextContent("••••••••");
    expect(screen.getByRole("button", { name: /Start bot/ })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Bot is idle on this account.");
  });

  it("shows live numbers while running", () => {
    card({ ...base, bot: { ...base.bot, status: "running", desired: "running", started_at: "2026-11-09T10:00:00Z" },
      live: { at: "2026-11-09T10:01:00Z", balance: 10000, equity: 10012.5, today_pnl: 12.5, floating_pnl: 12.5, bid: 4000,
        ask: 4000.25, market_open: true,
        positions: [{ ticket: 9, side: "BUY", lots: 0.01, open_price: 3990, sl: 3980, tp: 4010, profit: 12.5, leg: "B" }] } });
    expect(screen.getByText("Bot running")).toBeInTheDocument();
    expect(screen.getByText("$10,012.50")).toBeInTheDocument();
    expect(screen.getAllByText("+$12.50").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Stop bot/ })).toBeInTheDocument();
  });

  it("shows the error reason and the retry countdown", () => {
    const soon = new Date(Date.now() + 30000).toISOString();
    card({ ...base, bot: { ...base.bot, status: "error", desired: "running", reason: "broker disconnected: no route",
      retry_at: soon } });
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/broker disconnected: no route Retrying in (29|30) s/);
  });
});
