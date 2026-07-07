export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="section-eyebrow">{eyebrow}</p>
        <h2 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-3 max-w-lg text-sm leading-relaxed text-slate">
            {subtitle}
          </p>
        ) : null}
      </div>
      {children}
    </div>
  );
}
