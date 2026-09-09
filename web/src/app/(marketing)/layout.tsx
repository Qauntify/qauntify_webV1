import { Nav } from "@/components/shared/Nav";

/**
 * Shared chrome for public marketing routes. Soft-navigating between
 * /signals, /war-room, /track-record, /tools keeps Nav mounted and only
 * swaps the page segment — much faster than remounting auth+header each time.
 */
export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <Nav />
      {children}
    </>
  );
}
