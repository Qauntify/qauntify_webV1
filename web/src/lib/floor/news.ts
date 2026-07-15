const FEED_URLS = [
  "https://www.coindesk.com/arc/outboundfeeds/rss/",
  "https://www.fxstreet.com/rss/news",
];
const MAX_HEADLINES = 10;

function decodeTitle(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;|&apos;/g, "'")
    .trim();
}

function extractTitles(xml: string): string[] {
  return Array.from(xml.matchAll(/<title(?:\s[^>]*)?>([\s\S]*?)<\/title>/gi))
    .map((match) => decodeTitle(match[1]))
    .filter(Boolean);
}

export async function fetchHeadlinesBlock(): Promise<string> {
  try {
    const results = await Promise.allSettled(
      FEED_URLS.map(async (url) => {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(`RSS HTTP ${response.status}`);
        return extractTitles(await response.text());
      }),
    );
    const titles = results.flatMap((result) =>
      result.status === "fulfilled" ? result.value : [],
    );
    const unique = [...new Set(titles)].slice(0, MAX_HEADLINES);

    return unique.length ? unique.map((title) => `- ${title}`).join("\n") : "No headlines.";
  } catch {
    return "No headlines.";
  }
}
