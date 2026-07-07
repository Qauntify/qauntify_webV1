// One shape for every inline status message (form errors, saved/deleted
// confirmations). Tone picks the color pair; layout comes from the caller.
export function Notice({
  tone,
  children,
  className = "",
}: {
  tone: "success" | "error";
  children: React.ReactNode;
  className?: string;
}) {
  const tones =
    tone === "success" ? "bg-long-soft text-long" : "bg-short-soft text-short";
  return (
    <p className={`rounded-lg px-4 py-3 text-sm ${tones} ${className}`}>
      {children}
    </p>
  );
}
