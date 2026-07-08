import Link from "next/link";

export function Logo({
  suffix,
  className = "",
}: {
  suffix?: string;
  className?: string;
}) {
  return (
    <Link
      href="/"
      className={`inline-flex items-center gap-2.5 text-lg font-bold tracking-tight ${className}`}
    >
      <span
        className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white"
        aria-hidden
      >
        Q
      </span>
      <span className="text-ink">
        Qaunt<span className="text-accent">ify</span>
        {suffix ? (
          <span className="ml-1.5 text-xs font-medium text-slate">{suffix}</span>
        ) : null}
      </span>
    </Link>
  );
}
