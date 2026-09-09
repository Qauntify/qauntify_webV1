/** Shared Next.js Data Cache options for public (anon / RLS) reads.

Pages already declare `revalidate = 20|30|60`. Matching fetch options so
soft navigations hit the Data Cache instead of Supabase every time.
Authorization is part of the cache key, so signed-in JWTs stay isolated.
*/
export const PUBLIC_FETCH = { next: { revalidate: 30 } } as const;

/** Slightly fresher for war-room / dashboard streams. */
export const FRESH_FETCH = { next: { revalidate: 20 } } as const;

/** Track-record is heavier; 60s is enough for public browsing. */
export const SLOW_FETCH = { next: { revalidate: 60 } } as const;
