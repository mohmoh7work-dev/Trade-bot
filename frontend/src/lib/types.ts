export type User = {
  id: number;
  name: string;
  email: string;
  created_at: string;
  plan: { code: string; name: string } | null;
  telegram: { available: boolean; connected: boolean };
};

export type BotStatus = "stopped" | "starting" | "running" | "stopping" | "error";

export type Position = {
  ticket: number;
  side: "BUY" | "SELL";
  lots: number;
  open_price: number;
  sl: number;
  tp: number;
  profit: number | null;
  leg: string | null;
};

export type Window = { from: string; to: string };

export type BotSettings = {
  sizing: "risk" | "lot";
  risk_pct: number;
  lot: number;
  max_open_trades: number;
  max_spread: number;
  daily_loss_pct: number;
  max_drawdown_pct: number;
  trading_hours: Window[];
  close_on_stop: boolean;
};

export type Limits = {
  risk_pct: number;
  lot: number;
  max_open_trades: number;
  daily_loss_pct: number;
  max_drawdown_pct: number;
};

export type Account = {
  id: number;
  nickname: string;
  platform: "MT5";
  broker: string;
  server: string;
  login: string;
  symbol: string;
  mode: "auto" | "alerts";
  allow_live: boolean;
  account_type: "demo" | "real" | "contest" | null;
  currency: string | null;
  password_set: boolean;
  settings: BotSettings;
  bot: {
    status: BotStatus;
    desired: "running" | "stopped";
    reason: string | null;
    retry_at: string | null;
    started_at: string | null;
    heartbeat_at: string | null;
  };
  live: {
    at: string;
    balance: number | null;
    equity: number | null;
    today_pnl: number | null;
    floating_pnl: number | null;
    bid: number | null;
    ask: number | null;
    market_open: boolean | null;
    positions: Position[];
  } | null;
  last_event_id: number | null;
  created_at: string;
};

export type BotEvent = {
  id: number;
  at: string;
  kind: string;
  level: string;
  message: string;
};

export type Payment = {
  id: number;
  date: string;
  amount_cents: number;
  currency: string;
  plan: string | null;
  status: string;
  invoice_url: string | null;
};

export type DetectResult = {
  type: string | null;
  currency: string | null;
  balance: number | null;
  company: string | null;
  symbol: string | null;
  symbol_exact: boolean | null;
  symbols: string[];
};
