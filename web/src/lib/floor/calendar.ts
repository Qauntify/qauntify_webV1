const CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json";
const MAX_EVENTS = 10;

type CalendarEvent = {
  date?: string;
  country?: string;
  impact?: string;
  title?: string;
};

export async function fetchCalendarBlock(): Promise<string> {
  try {
    const response = await fetch(CALENDAR_URL, { cache: "no-store" });
    if (!response.ok) return "Calendar unavailable.";

    const events = (await response.json()) as unknown;
    if (!Array.isArray(events)) return "Calendar unavailable.";

    const lines = events
      .filter(
        (event): event is CalendarEvent =>
          typeof event === "object" && event !== null &&
          ["High", "Medium"].includes(String((event as CalendarEvent).impact)),
      )
      .slice(0, MAX_EVENTS)
      .map((event) =>
        [event.date, event.country, event.impact, event.title]
          .filter(Boolean)
          .join(" | "),
      )
      .filter(Boolean);

    return lines.length ? lines.map((line) => `- ${line}`).join("\n") : "Calendar unavailable.";
  } catch {
    return "Calendar unavailable.";
  }
}
