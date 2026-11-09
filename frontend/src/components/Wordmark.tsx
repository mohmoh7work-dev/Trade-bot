export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={"select-none text-xl font-extrabold tracking-tight text-brand-700 " + className}>
      mohz<span className="text-ink"> bot</span>
    </span>
  );
}
