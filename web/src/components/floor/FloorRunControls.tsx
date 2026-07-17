"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Notice } from "@/components/shared/Notice";
import type { FloorRunStatus } from "@/lib/floor/types";

const IDLE_STATUS: FloorRunStatus = {
  running: false,
  runId: null,
  cycle: 0,
  phase: "idle",
  lastMessage: "",
  lastSignal: null,
};

type RunResponse = {
  ok?: boolean;
  error?: string;
  message?: string;
  runId?: string;
};

export function FloorRunControls({
  onStatusChange,
  onCycleComplete,
}: {
  onStatusChange: (status: FloorRunStatus) => void;
  onCycleComplete: () => void;
}) {
  const [status, setStatus] = useState<FloorRunStatus>(IDLE_STATUS);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const prevRef = useRef({ running: false, cycle: 0 });

  const applyStatus = useCallback((next: FloorRunStatus) => {
    setStatus(next);
    onStatusChange(next);
  }, [onStatusChange]);

  const syncStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/admin/floor/run");
      if (!response.ok) return null;
      const payload = await response.json() as FloorRunStatus;

      const prev = prevRef.current;
      if (prev.running && !payload.running) {
        setToast("Gold hunter stopped.");
        onCycleComplete();
      } else if (payload.cycle > prev.cycle) {
        onCycleComplete();
      }
      prevRef.current = { running: payload.running, cycle: payload.cycle };

      applyStatus(payload);
      return payload;
    } catch {
      return null;
    }
  }, [applyStatus, onCycleComplete]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void syncStatus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [syncStatus]);

  useEffect(() => {
    if (!status.running) return undefined;

    const timer = window.setInterval(() => {
      void syncStatus();
    }, 2000);

    return () => window.clearInterval(timer);
  }, [status.running, syncStatus]);

  async function stopRun() {
    setError(null);
    try {
      await fetch("/api/admin/floor/stop", { method: "POST" });
      setToast("Stop requested — finishing current step...");
      void syncStatus();
    } catch {
      setError("Could not send stop request.");
    }
  }

  async function startRun() {
    setError(null);
    setToast(null);

    try {
      const response = await fetch("/api/admin/floor/run", { method: "POST" });
      const payload = await response.json() as RunResponse;

      if (!response.ok) {
        throw new Error(payload.error ?? "Could not start gold hunter.");
      }

      setToast(payload.message ?? "Gold hunter started.");
      await syncStatus();
      onCycleComplete();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Could not start gold hunter.");
    }
  }

  return (
    <section
      className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card p-4"
      aria-label="Floor run controls"
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink">Gold AI hunter</h2>
        <p className="mt-0.5 text-xs text-slate">
          {status.running
            ? "Four floor desks analyze gold; the PM AI drops a signal or passes. Runs until you press Stop."
            : "Start the hunter. It loops forever until you press Stop."}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {status.running ? (
          <button
            type="button"
            onClick={() => void stopRun()}
            className="rounded-lg border border-short/40 bg-short-soft px-4 py-2 text-sm font-medium text-short transition-colors hover:border-short/60"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void startRun()}
            className="btn-primary-sm"
          >
            Run
          </button>
        )}
      </div>

      {toast ? (
        <Notice tone="success" className="w-full">
          {toast}
        </Notice>
      ) : null}
      {error ? (
        <Notice tone="error" className="w-full">
          {error}
        </Notice>
      ) : null}
    </section>
  );
}
