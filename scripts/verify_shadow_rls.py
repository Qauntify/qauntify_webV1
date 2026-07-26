"""Prove shadow signals are invisible to the public before any are written.

Inserts a probe row with the service-role key, then reads it back through the
ANON key. Reading back with the service-role key would prove nothing — that key
bypasses RLS entirely, which is exactly the mistake this script exists to
prevent.

Two directions are checked, because a policy that hid EVERYTHING would pass a
naive "is the shadow hidden?" test:

  1. a shadow row must be invisible to anon
  2. an identical non-shadow row must still be VISIBLE to anon

The probe is written in a closed state (sl_hit) on purpose — that is the worst
case, matching both the 24-hour preview policy and the closed-trade policy.

Usage: .venv/bin/python -m scripts.verify_shadow_rls
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import requests

PROBE_SYMBOL = "ZZPROBE"


def load_env(path=".env"):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _probe_row(probe_id, shadow):
    return {
        "id": probe_id,
        "symbol": PROBE_SYMBOL,
        "timeframe": "15m",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "take_profit_1": 102.0,
        "confidence": 50,
        "rationale": "RLS containment probe — safe to delete",
        "indicators": {},
        "news_headlines": [],
        "status": "sl_hit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "shadow": shadow,
    }


def _visible_to_anon(url, anon, probe_id):
    """(direct_fetch_visible, appears_in_listing) as seen by the anon role."""
    headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
    direct = requests.get(
        f"{url}/rest/v1/signals?id=eq.{probe_id}&select=id",
        headers=headers, timeout=30,
    ).json()
    listing = requests.get(
        f"{url}/rest/v1/signals?select=id&limit=1000",
        headers=headers, timeout=30,
    ).json()
    in_listing = any(
        isinstance(x, dict) and x.get("id") == probe_id for x in listing
    )
    return bool(direct), in_listing


def _run_probe(url, svc, anon, shadow):
    probe_id = str(uuid.uuid4())
    headers = {
        "apikey": svc, "Authorization": f"Bearer {svc}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    }
    resp = requests.post(f"{url}/rest/v1/signals",
                         json=_probe_row(probe_id, shadow),
                         headers=headers, timeout=30)
    if resp.status_code >= 400:
        if "shadow" in resp.text:
            sys.exit("FAIL: the `shadow` column does not exist — apply the "
                     "migration in supabase/schema.sql first.\n"
                     f"  server said: {resp.text[:200]}")
        sys.exit(f"FAIL: could not insert probe: {resp.status_code} "
                 f"{resp.text[:200]}")
    try:
        return _visible_to_anon(url, anon, probe_id)
    finally:
        requests.delete(
            f"{url}/rest/v1/signals?id=eq.{probe_id}",
            headers={"apikey": svc, "Authorization": f"Bearer {svc}"},
            timeout=30,
        )


def main():
    env = {**load_env(), **os.environ}
    url = env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL", "")
    svc = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    anon = (env.get("SUPABASE_ANON_KEY")
            or env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", ""))
    if not url or not svc or not anon:
        sys.exit("need SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and an anon key")

    print("Probe 1: shadow row MUST be invisible to anon")
    s_direct, s_listing = _run_probe(url, svc, anon, shadow=True)
    print(f"  direct fetch visible : {s_direct}")
    print(f"  appears in listing   : {s_listing}")

    print("\nProbe 2: non-shadow row MUST still be visible to anon")
    v_direct, v_listing = _run_probe(url, svc, anon, shadow=False)
    print(f"  direct fetch visible : {v_direct}")
    print(f"  appears in listing   : {v_listing}")

    failures = []
    if s_direct or s_listing:
        failures.append("a SHADOW row is visible to anon — containment broken")
    if not v_direct:
        failures.append("a NORMAL row is hidden from anon — the policy is too "
                        "strict and would break the public track record")
    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        sys.exit(1)
    print("PASS: shadows are contained and normal signals still public")


if __name__ == "__main__":
    main()
