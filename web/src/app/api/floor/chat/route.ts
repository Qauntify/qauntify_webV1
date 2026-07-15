import { NextResponse } from "next/server";

import { checkAndRecordFloorChat, formatFloorBoardPack } from "@/lib/floor/chat";
import { formatSignalsBlock } from "@/lib/floor/context";
import { floorChat, parseDeskBrief } from "@/lib/floor/llm";
import { buildPmChatMessages } from "@/lib/floor/prompts";
import { fetchSignalSnapshots, insertFloorChatAssistant } from "@/lib/floor/store";
import {
  FLOOR_DESKS,
  type FloorBrief,
  type FloorChatMessage,
  type FloorDesk,
  type FloorTone,
} from "@/lib/floor/types";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const PM_UNAVAILABLE = "Floor PM unavailable. Please try again shortly.";

type FloorBriefRow = {
  id: string;
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  run_id: string;
  created_at: string;
};

type FloorChatRow = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

function mapFloorBrief(row: FloorBriefRow): FloorBrief {
  return {
    id: row.id,
    desk: row.desk,
    tone: row.tone,
    body: row.body,
    runId: row.run_id,
    createdAt: row.created_at,
  };
}

function mapFloorChatMessage(row: FloorChatRow): FloorChatMessage {
  return {
    id: row.id,
    role: row.role,
    content: row.content,
    createdAt: row.created_at,
  };
}

async function loadBoardPack(
  supabase: Awaited<ReturnType<typeof createClient>>,
): Promise<FloorBrief[]> {
  const { data, error } = await supabase
    .from("floor_briefs")
    .select("id, desk, tone, body, run_id, created_at")
    .order("created_at", { ascending: false })
    .limit(40);
  if (error) throw new Error("Could not load floor board");

  const latestByDesk = new Map<FloorDesk, FloorBrief>();
  for (const row of (data ?? []) as FloorBriefRow[]) {
    if (!latestByDesk.has(row.desk)) latestByDesk.set(row.desk, mapFloorBrief(row));
  }

  return FLOOR_DESKS.flatMap((desk) => {
    const brief = latestByDesk.get(desk);
    return brief ? [brief] : [];
  });
}

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("floor_chat_messages")
    .select("id, role, content, created_at")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(50);
  if (error) {
    return NextResponse.json({ error: "Could not load floor chat" }, { status: 500 });
  }

  const messages = ((data ?? []) as FloorChatRow[]).reverse().map(mapFloorChatMessage);
  return NextResponse.json({ messages });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const message = typeof body?.message === "string" ? body.message.trim() : "";
  if (!message) {
    return NextResponse.json({ error: "Message is required" }, { status: 400 });
  }
  if (message.length > 1_000) {
    return NextResponse.json({ error: "Message must be 1000 characters or fewer" }, { status: 400 });
  }
  if (!checkAndRecordFloorChat(user.id)) {
    return NextResponse.json({ error: "Too many messages. Please wait a moment." }, { status: 429 });
  }

  const { data: userRow, error: userInsertError } = await supabase
    .from("floor_chat_messages")
    .insert({ user_id: user.id, role: "user", content: message })
    .select("id, role, content, created_at")
    .single();
  if (userInsertError || !userRow) {
    return NextResponse.json({ error: "Could not save floor chat message" }, { status: 500 });
  }

  let assistantContent = PM_UNAVAILABLE;
  try {
    const [briefs, signals] = await Promise.all([
      loadBoardPack(supabase),
      fetchSignalSnapshots(),
    ]);
    const reply = await floorChat(
      buildPmChatMessages({
        question: message,
        boardPack: formatFloorBoardPack(briefs),
        signalsBlock: formatSignalsBlock(signals),
      }),
    );
    assistantContent = parseDeskBrief(reply).body;
  } catch {
    assistantContent = PM_UNAVAILABLE;
  }

  try {
    const assistant = await insertFloorChatAssistant({
      userId: user.id,
      content: assistantContent,
    });
    return NextResponse.json({
      user: mapFloorChatMessage(userRow as FloorChatRow),
      assistant,
    });
  } catch {
    return NextResponse.json({ error: "Could not save floor chat response" }, { status: 500 });
  }
}
