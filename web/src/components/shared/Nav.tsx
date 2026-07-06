import Link from "next/link";

const links = [
  { href: "/#features", label: "Features" },
  { href: "/#signals", label: "Signals" },
  { href: "/#markets", label: "Markets" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="font-display text-xl tracking-tight">
          Think<span className="italic">Trade</span>
        </Link>
        <nav className="hidden items-center gap-7 text-sm text-slate md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/dashboard"
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink/85"
        >
          Dashboard
        </Link>
      </div>
    </header>
  );
}
