const DEFAULT_REPO = "Qauntify/qauntify_webV1";
const WORKFLOW_FILE = "engine.yml";
const XAU_SCALPER_EVENT_TYPE = "run-xau-scalper";

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

export async function dispatchEngineWorkflow(): Promise<DispatchResult> {
  const target = resolveGithubTarget();
  if ("error" in target) return target.error;
  const { token, owner, name } = target;

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${name}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
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

/** Restarts the XAU scalper via the repository_dispatch event xau-scalper.yml
 * already listens for — used by the watchdog when its heartbeat goes stale. */
export async function dispatchXauScalperRestart(): Promise<DispatchResult> {
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
      body: JSON.stringify({ event_type: XAU_SCALPER_EVENT_TYPE }),
      cache: "no-store",
    },
  );

  return dispatchResult(response);
}
