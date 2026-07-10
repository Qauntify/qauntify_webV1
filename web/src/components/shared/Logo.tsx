import Image from "next/image";
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
      <Image
        src="/logo/logo.png"
        alt=""
        width={32}
        height={32}
        priority
        className="h-8 w-8"
        aria-hidden
      />
      <span className="text-ink">
        Qaunt<span className="text-accent">ify</span>
        {suffix ? (
          <span className="ml-1.5 text-xs font-medium text-slate">{suffix}</span>
        ) : null}
      </span>
    </Link>
  );
}
