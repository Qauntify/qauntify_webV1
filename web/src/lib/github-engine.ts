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

function resolveGithubTarget():
  | { token: string; owner: string; name: string }
  | { error: DispatchResult } {
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

/** workflow_dispatch on engine.yml (cron-job.org primary path). */
export async function dispatchEngineWorkflow(): Promise<DispatchResult> {
  const target = resolveGithubTarget();
  if ("error" in target) return target.error;
  const { token, owner, name } = target;

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
      body: JSON.stringify({ ref: "main" }),
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
