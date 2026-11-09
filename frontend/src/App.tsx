import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import AuthPage from "./pages/AuthPage";
import AccountsPage from "./pages/AccountsPage";
import PaymentsPage from "./pages/PaymentsPage";
import ProfilePage from "./pages/ProfilePage";
import { IconReceipt, IconUser, IconWallet, Spinner } from "./components/Icons";
import { Wordmark } from "./components/Wordmark";

const NAV = [
  { to: "/", label: "Broker accounts", short: "Accounts", icon: IconWallet },
  { to: "/payments", label: "Payment history", short: "Payments", icon: IconReceipt },
  { to: "/account", label: "Account details", short: "Account", icon: IconUser },
];

function Shell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return (
    <div className="min-h-screen pb-24 sm:pb-10">
      <header className="sticky top-0 z-30 border-b border-white/40 bg-[#f8d3d4]/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4 sm:h-16 sm:px-6">
          <NavLink to="/" aria-label="mohz bot home"><Wordmark /></NavLink>
          <nav className="hidden items-center gap-1 sm:flex" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end
                className={({ isActive }) => "rounded-xl px-3.5 py-2 text-sm font-semibold transition " +
                  (isActive ? "bg-white text-brand-700 shadow-sm" : "text-ink-soft hover:bg-white/60 hover:text-brand-700")}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <span className="truncate text-sm font-medium text-ink-soft sm:hidden">{user?.name}</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pt-5 sm:px-6 sm:pt-8">{children}</main>
      <nav aria-label="Main" className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-brand-100 bg-white/95 backdrop-blur sm:hidden">
        <div className="mx-auto grid max-w-md grid-cols-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end
              className={({ isActive }) => "flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-semibold " +
                (isActive ? "text-brand-700" : "text-ink-faint")}>
              <n.icon className="h-6 w-6" />
              {n.short}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-brand-700">
        <Spinner className="h-7 w-7" />
      </div>
    );
  }
  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<AuthPage mode="login" />} />
      </Routes>
    );
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<AccountsPage />} />
        <Route path="/payments" element={<PaymentsPage />} />
        <Route path="/account" element={<ProfilePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
