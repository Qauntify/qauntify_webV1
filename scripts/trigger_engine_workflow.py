#!/usr/bin/env python3
"""Trigger the signals engine GitHub Actions workflow.

Usage:
  GITHUB_DISPATCH_TOKEN=ghp_... python scripts/trigger_engine_workflow.py

Or call the deployed cron endpoint:
  ENGINE_CRON_SECRET=... python scripts/trigger_engine_workflow.py --via-web
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request


DEFAULT_REPO = "Qauntify/qauntify_webV1"
DEFAULT_WEB_URL = "https://web-seven-pi-76.vercel.app/api/cron/trigger-engine"


def _github_dispatch(token: str, repo: str) -> None:
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/actions/workflows/engine.yml/dispatches"
    body = b'{"ref":"main"}'
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise RuntimeError(f"Unexpected status {response.status}")


def _web_trigger(secret: str, base_url: str) -> None:
    url = f"{base_url.rstrip('/')}?secret={secret}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected status {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger the signals engine workflow")
    parser.add_argument(
        "--via-web",
        action="store_true",
        help="Call the Vercel cron endpoint instead of GitHub directly",
    )
    parser.add_argument(
        "--web-url",
        default=os.getenv("ENGINE_CRON_URL", DEFAULT_WEB_URL),
        help="Cron endpoint base URL (with --via-web)",
    )
    args = parser.parse_args()

    try:
        if args.via_web:
            secret = os.getenv("ENGINE_CRON_SECRET", "").strip()
            if not secret:
                print("ENGINE_CRON_SECRET is not set", file=sys.stderr)
                return 2
            _web_trigger(secret, args.web_url)
            print("Engine triggered via web cron endpoint.")
            return 0

        token = os.getenv("GITHUB_DISPATCH_TOKEN", "").strip()
        if not token:
            print("GITHUB_DISPATCH_TOKEN is not set", file=sys.stderr)
            return 2
        repo = os.getenv("GITHUB_REPO", DEFAULT_REPO).strip()
        _github_dispatch(token, repo)
        print(f"Engine workflow dispatched for {repo}.")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
