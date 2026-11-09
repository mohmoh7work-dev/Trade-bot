type P = { className?: string };
const base = "h-5 w-5";

function Svg({ className, children }: P & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
      strokeLinejoin="round" className={className ?? base} aria-hidden="true">
      {children}
    </svg>
  );
}

export const IconPencil = (p: P) => (
  <Svg {...p}><path d="M16.9 3.6a2.1 2.1 0 0 1 3 3L8.5 18 4 19.5 5.5 15z" /><path d="m15 5.5 3.5 3.5" /></Svg>
);
export const IconTrash = (p: P) => (
  <Svg {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></Svg>
);
export const IconSliders = (p: P) => (
  <Svg {...p}><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" />
    <circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></Svg>
);
export const IconList = (p: P) => (
  <Svg {...p}><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></Svg>
);
export const IconEye = (p: P) => (
  <Svg {...p}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></Svg>
);
export const IconEyeOff = (p: P) => (
  <Svg {...p}><path d="M3 3l18 18M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.9 9.9 0 0 0 5.4-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></Svg>
);
export const IconX = (p: P) => (
  <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>
);
export const IconPlus = (p: P) => (
  <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
);
export const IconPlay = (p: P) => (
  <Svg {...p}><path d="M7 5v14l11-7z" fill="currentColor" stroke="none" /></Svg>
);
export const IconStop = (p: P) => (
  <Svg {...p}><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" /></Svg>
);
export const IconLink = (p: P) => (
  <Svg {...p}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></Svg>
);
export const IconSearch = (p: P) => (
  <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></Svg>
);
export const IconWallet = (p: P) => (
  <Svg {...p}><path d="M4 7a2 2 0 0 1 2-2h12v4M4 7v10a2 2 0 0 0 2 2h14V9H6a2 2 0 0 1-2-2z" /><path d="M16 14h.01" /></Svg>
);
export const IconReceipt = (p: P) => (
  <Svg {...p}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3" /></Svg>
);
export const IconUser = (p: P) => (
  <Svg {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></Svg>
);
export const IconLogout = (p: P) => (
  <Svg {...p}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3" /></Svg>
);

export function Spinner({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={(className ?? "h-4 w-4") + " animate-spin"} aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}
