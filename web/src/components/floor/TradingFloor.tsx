"use client";

import { useEffect, useState } from "react";

import type { FloorBrief } from "@/lib/floor/types";
import { DeskBoard } from "./DeskBoard";
import { FloorChat } from "./FloorChat";

type BoardResponse = { desks: FloorBrief[]; error?: string };

export function TradingFloor() {
  const [desks, setDesks] = useState<FloorBrief[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingBoard, setIsLoadingBoard] = useState(true);

  useEffect(() => {
    let isCurrent = true;

    async function loadBoard() {
      try {
        const response = await fetch("/api/floor/board");
        const payload = await response.json() as BoardResponse;
        if (!response.ok) throw new Error(payload.error ?? "Could not load desk board.");
        if (isCurrent) setDesks(payload.desks);
      } catch (loadError) {
        if (isCurrent) {
          setError(loadError instanceof Error ? loadError.message : "Could not load desk board.");
        }
      } finally {
        if (isCurrent) setIsLoadingBoard(false);
      }
    }

    void loadBoard();
    return () => {
      isCurrent = false;
    };
  }, []);

  return (
    <div className="space-y-8">
      {error ? <p className="text-sm text-ink" role="alert">{error}</p> : null}
      {!error || desks.length > 0 ? (
        <DeskBoard desks={desks} isLoading={isLoadingBoard} />
      ) : null}
      <FloorChat />
    </div>
  );
}
