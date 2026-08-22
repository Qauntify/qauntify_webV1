import type { EngineHtf } from "@/lib/bar-close";

const DEFAULT_REPO = "Qauntify/qauntify_webV1";
const ENGINE_WORKFLOW_FILE = "engine.yml";

export const REPO_EVENTS = {
  engine: "run-engine",
  xauScalper: "run-xau-scalper",
  warRoom: "run-war-room",
  healthcheck: "run-session-healthcheck",
} as const;

export type DispatchResult =
  | { ok: true }
  | { ok: false; status: number; message: string };

type DispatchFailure = Extract<DispatchResult, { ok: false }>;

function resolveGithubTarget():
  | { token: string; owner: string; name: string }
  | { error: DispatchFailure } {
  const token = process.env.GITHUB_DISPATCH_TOKEN?.trim();
  const repo = (process.env.GITHUB_REPO ?? DEFAULT_REPO).trim();

  if (!token) {
    return {
      error: { ok: false, status: 500, message: "GITHUB_DISPATCH_TOKEN is not set" },
    };
  }

  const [owner, name] = repo.split("/");
  if (!owner || !name) {
    return {
      error: { ok: false, status: 500, message: "GITHUB_REPO must be owner/repo" },
    };
  }

  return { token, owner, name };
}

async function dispatchResult(response: Response): Promise<DispatchResult> {
  if (response.status === 204) {
    return { ok: true };
  }

  const body = await response.text();
  return {
    ok: false,
    status: response.status,
    message: body.slice(0, 300) || response.statusText,
  };
}

export type EngineDispatchOptions = {
  /** When set, only scan sessions whose timeframe closed (5m / 15m / 1h). */
  due?: EngineHtf[];
};

/** workflow_dispatch on engine.yml (cron-job.org primary path). */
export async function dispatchEngineWorkflow(
  opts?: EngineDispatchOptions,
): Promise<DispatchResult> {
  const target = resolveGithubTarget();
  if ("error" in target) return target.error;
  const { token, owner, name } = target;

  const payload: { ref: string; inputs?: { sessions: string } } = {
    ref: "main",
  };
  if (opts?.due?.length) {
    payload.inputs = { sessions: opts.due.join(",") };
  }

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${name}/actions/workflows/${ENGINE_WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    },
  );

  return dispatchResult(response);
}

async function dispatchRepositoryEvent(eventType: string): Promise<DispatchResult> {
  const target = resolveGithubTarget();
  if ("error" in target) return target.error;
  const { token, owner, name } = target;

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${name}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ event_type: eventType }),
      cache: "no-store",
    },
  );

  return dispatchResult(response);
}

/** Restarts the XAU scalper — used by cron-job.org and the heartbeat watchdog. */
export async function dispatchXauScalperRestart(): Promise<DispatchResult> {
  return dispatchRepositoryEvent(REPO_EVENTS.xauScalper);
}

export async function dispatchWarRoomWorkflow(): Promise<DispatchResult> {
  return dispatchRepositoryEvent(REPO_EVENTS.warRoom);
}

export async function dispatchHealthcheckWorkflow(): Promise<DispatchResult> {
  return dispatchRepositoryEvent(REPO_EVENTS.healthcheck);
}

/** Cron workflows we monitor in Admin → Cron. */
export const CRON_WORKFLOWS = [
  {
    key: "engine",
    file: "engine.yml",
    label: "Signals engine",
    trigger: "/api/cron/trigger-engine",
  },
  {
    key: "war-room",
    file: "war-room.yml",
    label: "War Room floor",
    trigger: "/api/cron/trigger-war-room",
  },
  {
    key: "xau-scalper",
    file: "xau-scalper.yml",
    label: "XAUUSD 1m scalper",
    trigger: "/api/cron/trigger-xau-scalper",
  },
  {
    key: "healthcheck",
    file: "session-healthcheck.yml",
    label: "Session healthcheck",
    trigger: "/api/cron/trigger-healthcheck",
  },
] as const;

export type WorkflowRunSummary = {
  id: number;
  name: string;
  status: string | null;
  conclusion: string | null;
  html_url: string;
  created_at: string;
  updated_at: string;
  run_number: number;
  event: string;
  head_branch: string | null;
};

export type CronWorkflowStatus = {
  key: string;
  label: string;
  file: string;
  trigger: string;
  runs: WorkflowRunSummary[];
  error?: string;
};

type GhWorkflowRun = {
  id: number;
  name: string;
  status: string | null;
  conclusion: string | null;
  html_url: string;
  created_at: string;
  updated_at: string;
  run_number: number;
  event: string;
  head_branch: string | null;
};

async function listWorkflowRuns(
  workflowFile: string,
  perPage: number,
): Promise<{ ok: true; runs: WorkflowRunSummary[] } | { ok: false; message: string }> {
  const target = resolveGithubTarget();
  if ("error" in target) {
    return { ok: false, message: target.error.message };
  }
  const { token, owner, name } = target;

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${name}/actions/workflows/${workflowFile}/runs?per_page=${perPage}`,
    {
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.text();
    return {
      ok: false,
      message: body.slice(0, 200) || response.statusText,
    };
  }

  const data = (await response.json()) as { workflow_runs?: GhWorkflowRun[] };
  const runs = (data.workflow_runs ?? []).map((r) => ({
    id: r.id,
    name: r.name,
    status: r.status,
    conclusion: r.conclusion,
    html_url: r.html_url,
    created_at: r.created_at,
    updated_at: r.updated_at,
    run_number: r.run_number,
    event: r.event,
    head_branch: r.head_branch,
  }));

  return { ok: true, runs };
}

/** Latest GitHub Actions runs for every cron-backed workflow. */
export async function listCronStatuses(
  perPage = 5,
): Promise<CronWorkflowStatus[]> {
  return Promise.all(
    CRON_WORKFLOWS.map(async (wf) => {
      const result = await listWorkflowRuns(wf.file, perPage);
      if (!result.ok) {
        return {
          key: wf.key,
          label: wf.label,
          file: wf.file,
          trigger: wf.trigger,
          runs: [],
          error: result.message,
        };
      }
      return {
        key: wf.key,
        label: wf.label,
        file: wf.file,
        trigger: wf.trigger,
        runs: result.runs,
      };
    }),
  );
}
