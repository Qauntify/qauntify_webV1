import type { FloorGoldSignal, FloorRunPhase, FloorRunStatus } from "./types";

type FloorRunState = {
  running: boolean;
  cancelRequested: boolean;
  runId: string | null;
  cycle: number;
  phase: FloorRunPhase;
  lastMessage: string;
  lastSignal: FloorGoldSignal | null;
};

let state: FloorRunState = {
  running: false,
  cancelRequested: false,
  runId: null,
  cycle: 0,
  phase: "idle",
  lastMessage: "",
  lastSignal: null,
};

export type FloorRunSnapshot = FloorRunStatus;

export function floorRunSnapshot(): FloorRunSnapshot {
  return {
    running: state.running,
    runId: state.runId,
    cycle: state.cycle,
    phase: state.phase,
    lastMessage: state.lastMessage,
    lastSignal: state.lastSignal,
  };
}

export function beginFloorRun(runId: string): boolean {
  if (state.running) return false;
  state = {
    running: true,
    cancelRequested: false,
    runId,
    cycle: 0,
    phase: "macro",
    lastMessage: "Gold hunter started.",
    lastSignal: null,
  };
  return true;
}

export function requestFloorStop(): void {
  if (state.running) {
    state.cancelRequested = true;
    state.lastMessage = "Stop requested — finishing current step...";
  }
}

export function shouldStopFloorRun(): boolean {
  return state.cancelRequested;
}

export function setFloorRunPhase(phase: FloorRunPhase, message: string): void {
  state.phase = phase;
  state.lastMessage = message;
}

export function incrementFloorCycle(): number {
  state.cycle += 1;
  return state.cycle;
}

export function recordFloorSignal(signal: FloorGoldSignal): void {
  state.lastSignal = signal;
}

export function endFloorRun(): void {
  state = {
    running: false,
    cancelRequested: false,
    runId: null,
    cycle: 0,
    phase: "idle",
    lastMessage: "",
    lastSignal: state.lastSignal,
  };
}

export function resetFloorRunState(): void {
  state.lastSignal = null;
  endFloorRun();
}
