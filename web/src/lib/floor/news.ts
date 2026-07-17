/** Floor-only headlines — independent from the Python signals engine RSS client. */
const RSS_FEED_URLS = [
  "https://www.forexlive.com/feed/news",
  "https://www.fxstreet.com/rss/news",
];
const MAX_HEADLINES = 12;

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

async function fetchRssHeadlines(): Promise<string[]> {
  const results = await Promise.allSettled(
    RSS_FEED_URLS.map(async (url) => {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`RSS HTTP ${response.status}`);
      return extractTitles(await response.text());
    }),
  );
  return results.flatMap((result) =>
    result.status === "fulfilled" ? result.value : [],
  );
}

async function fetchCryptoPanicHeadlines(): Promise<string[]> {
  const key = process.env.CRYPTOPANIC_API_KEY?.trim();
  if (!key) return [];

  const url = new URL("https://cryptopanic.com/api/v1/posts/");
  url.searchParams.set("auth_token", key);
  url.searchParams.set("public", "true");
  url.searchParams.set("kind", "news");

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`CryptoPanic HTTP ${response.status}`);

  const payload = (await response.json()) as {
    results?: { title?: string }[];
  };
  return (payload.results ?? [])
    .map((item) => item.title?.trim())
    .filter((title): title is string => Boolean(title));
}

export async function fetchHeadlinesBlock(): Promise<string> {
  try {
    const [cryptoPanic, rss] = await Promise.all([
      fetchCryptoPanicHeadlines().catch(() => [] as string[]),
      fetchRssHeadlines(),
    ]);
    const unique = [...new Set([...cryptoPanic, ...rss])].slice(0, MAX_HEADLINES);

    return unique.length ? unique.map((title) => `- ${title}`).join("\n") : "No headlines.";
  } catch {
    return "No headlines.";
  }
}
