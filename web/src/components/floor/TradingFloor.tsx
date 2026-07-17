"use client";

import { useCallback, useEffect, useState } from "react";

import type { FloorBrief, FloorGoldSignal, FloorRunStatus } from "@/lib/floor/types";
import { Notice } from "@/components/shared/Notice";
import { GoldFloorBoard } from "./GoldFloorBoard";
import { FloorRunControls } from "./FloorRunControls";
import { FloorRobot } from "./FloorRobot";

type BoardResponse = {
  symbol: string;
  desks: FloorBrief[];
  lastSignal: FloorGoldSignal | null;
  scanLine: string;
  error?: string;
};

const IDLE_STATUS: FloorRunStatus = {
  running: false,
  runId: null,
  cycle: 0,
  phase: "idle",
  lastMessage: "",
  lastSignal: null,
};

export function TradingFloor() {
  const [symbol, setSymbol] = useState("PAXGUSDT");
  const [desks, setDesks] = useState<FloorBrief[]>([]);
  const [boardLastSignal, setBoardLastSignal] = useState<FloorGoldSignal | null>(null);
  const [scanLine, setScanLine] = useState("Press Run to start the gold AI hunter.");
  const [error, setError] = useState<string | null>(null);
  const [isLoadingBoard, setIsLoadingBoard] = useState(true);
  const [runStatus, setRunStatus] = useState<FloorRunStatus>(IDLE_STATUS);

  const loadBoard = useCallback(async () => {
    setIsLoadingBoard(true);
    setError(null);
    try {
      const response = await fetch("/api/floor/board");
      const payload = await response.json() as BoardResponse;
      if (!response.ok) throw new Error(payload.error ?? "Could not load gold floor.");
      setSymbol(payload.symbol);
      setDesks(payload.desks);
      setBoardLastSignal(payload.lastSignal);
      setScanLine(payload.scanLine);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load gold floor.");
    } finally {
      setIsLoadingBoard(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadBoard();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadBoard]);

  useEffect(() => {
    if (!runStatus.running) return undefined;
    const timer = window.setInterval(() => {
      void loadBoard();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [runStatus.running, loadBoard]);

  const lastSignal = runStatus.lastSignal ?? boardLastSignal;

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <FloorRunControls
        onStatusChange={setRunStatus}
        onCycleComplete={() => void loadBoard()}
      />
      <FloorRobot status={runStatus} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <GoldFloorBoard
        symbol={symbol}
        desks={desks}
        lastSignal={lastSignal}
        scanLine={scanLine}
        isLoading={isLoadingBoard}
        isHunting={runStatus.running}
        phase={runStatus.phase}
      />
    </div>
  );
}
