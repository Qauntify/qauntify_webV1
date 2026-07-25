"""Uploads a rendered chart PNG to Supabase Storage; returns the public URL."""
import requests

BUCKET = "signal-charts"


def upload_chart(png: bytes, signal_id: str, supabase_url: str,
                 service_key: str, session=None, suffix: str = "") -> str:
    """Upsert `{signal_id}{suffix}.png` into the public bucket; return its URL."""
    session = session or requests.Session()
    path = f"{signal_id}{suffix}.png"
    response = session.post(
        f"{supabase_url}/storage/v1/object/{BUCKET}/{path}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
        data=png,
        timeout=20,
    )
    response.raise_for_status()
    return f"{supabase_url}/storage/v1/object/public/{BUCKET}/{path}"
