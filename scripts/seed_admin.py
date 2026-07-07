import os
import sys
from typing import Any

import requests


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _supabase_base_url(url: str) -> str:
    return url.rstrip("/")


def _headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


def upsert_user(email: str, password: str, *, supabase_url: str, service_role_key: str) -> str:
    """Create user if absent; otherwise update password. Returns user id."""
    base = _supabase_base_url(supabase_url)
    session = requests.Session()

    # 1) Try to find the user by email (admin endpoint).
    list_resp = session.get(
        f"{base}/auth/v1/admin/users",
        headers=_headers(service_role_key),
        params={"email": email, "per_page": "1"},
        timeout=30,
    )
    list_resp.raise_for_status()
    body: Any = list_resp.json()
    users = body.get("users") if isinstance(body, dict) else None
    existing = users[0] if isinstance(users, list) and users else None
    user_id = existing.get("id") if isinstance(existing, dict) else None

    if user_id:
        patch_resp = session.put(
            f"{base}/auth/v1/admin/users/{user_id}",
            headers=_headers(service_role_key),
            json={
                "password": password,
                "email_confirm": True,
            },
            timeout=30,
        )
        patch_resp.raise_for_status()
        return str(user_id)

    # 2) Create new user.
    create_resp = session.post(
        f"{base}/auth/v1/admin/users",
        headers=_headers(service_role_key),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    created: Any = create_resp.json()
    created_id = created.get("id") if isinstance(created, dict) else None
    if not created_id:
        raise RuntimeError("Create user succeeded but response had no id")
    return str(created_id)


def main() -> int:
    # Usage:
    #   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python scripts/seed_admin.py admin@gmail.com
    # Then enter password via prompt (keeps it out of shell history).
    if len(sys.argv) != 2:
        print("Usage: python scripts/seed_admin.py <email>")
        return 2

    email = sys.argv[1].strip().lower()
    if "@" not in email:
        print("Invalid email.")
        return 2

    try:
        import getpass

        password = getpass.getpass("Password (won't echo): ").strip()
    except Exception:
        print("Could not read password from prompt.")
        return 2

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return 2

    try:
        supabase_url = _env("SUPABASE_URL")
        service_role_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    except RuntimeError as exc:
        print(str(exc))
        return 2

    try:
        user_id = upsert_user(
            email,
            password,
            supabase_url=supabase_url,
            service_role_key=service_role_key,
        )
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"Supabase request failed (HTTP {status}).")
        return 1
    except Exception as exc:
        print(f"Failed: {type(exc).__name__}: {exc}")
        return 1

    print(f"Seeded user: {email} (id={user_id})")
    print("Reminder: to access /admin, set ADMIN_EMAILS to include this email in Vercel env vars.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

