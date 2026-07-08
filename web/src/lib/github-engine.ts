const DEFAULT_REPO = "Qauntify/qauntify_webV1";
const WORKFLOW_FILE = "engine.yml";

export type DispatchResult =
  | { ok: true }
  | { ok: false; status: number; message: string };

export async function dispatchEngineWorkflow(): Promise<DispatchResult> {
  const token = process.env.GITHUB_DISPATCH_TOKEN?.trim();
  const repo = (process.env.GITHUB_REPO ?? DEFAULT_REPO).trim();

  if (!token) {
    return { ok: false, status: 500, message: "GITHUB_DISPATCH_TOKEN is not set" };
  }

  const [owner, name] = repo.split("/");
  if (!owner || !name) {
    return { ok: false, status: 500, message: "GITHUB_REPO must be owner/repo" };
  }

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
