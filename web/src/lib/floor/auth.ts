export function floorCronAuthorized(request: Request, secret: string): boolean {
  const trimmed = secret.trim();
  if (!trimmed) return false;

  if (request.headers.get("authorization") === `Bearer ${trimmed}`) {
    return true;
  }

  return new URL(request.url).searchParams.get("secret") === trimmed;
}
