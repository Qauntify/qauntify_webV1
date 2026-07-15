import type { FloorBrief } from "./types";

const floorChatTimestamps = new Map<string, number[]>();

export function allowFloorChat(
  timestamps: number[],
  now: number,
  limit = 6,
  windowMs = 60_000,
): boolean {
  return timestamps.filter((timestamp) => timestamp > now - windowMs && timestamp <= now).length < limit;
}

export function checkAndRecordFloorChat(userId: string, now = Date.now()): boolean {
  const timestamps = (floorChatTimestamps.get(userId) ?? []).filter(
    (timestamp) => timestamp > now - 60_000 && timestamp <= now,
  );
  const allowed = allowFloorChat(timestamps, now);

  if (allowed) timestamps.push(now);
  if (timestamps.length) floorChatTimestamps.set(userId, timestamps);
  else floorChatTimestamps.delete(userId);

  return allowed;
}

export function formatFloorBoardPack(briefs: FloorBrief[]): string {
  if (!briefs.length) return "No current desk briefs are available.";
  return briefs.map((brief) => `${brief.desk} (${brief.tone}): ${brief.body}`).join("\n");
}
