"""Seed playbook_chunks in Supabase with SEA-LION embeddings.

Usage:
  python -m signals.rag.seed
Requires schema playbook bits applied and SEALION + Supabase env vars.
"""
import uuid
from datetime import datetime, timezone

import requests

from signals.config import load_config
from signals.llm_client import SeaLionClient
from signals.rag.playbook import PLAYBOOK_CHUNKS


def upsert_playbook_chunk(
    chunk: dict,
    embedding: list,
    supabase_url: str,
    service_key: str,
    *,
    session=None,
) -> None:
    session = session or requests.Session()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL,
                             f"{chunk['strategy']}:{chunk['title']}")),
        "strategy": chunk["strategy"],
        "title": chunk["title"],
        "body": chunk["body"],
        "embedding": embedding,
        "updated_at": now,
    }
    response = session.post(
        f"{supabase_url}/rest/v1/playbook_chunks",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def seed_playbook(cfg=None, llm=None, session=None) -> int:
    cfg = cfg or load_config()
    llm = llm or SeaLionClient(
        cfg.sealion_api_key,
        model=cfg.sealion_model,
        base_url=cfg.sealion_base_url,
        session=session,
    )
    session = session or requests.Session()
    count = 0
    for chunk in PLAYBOOK_CHUNKS:
        text = f"{chunk['title']}\n{chunk['body']}"
        embedding = llm.embed(text)
        upsert_playbook_chunk(
            chunk, embedding, cfg.supabase_url, cfg.supabase_service_key,
            session=session,
        )
        count += 1
        print(f"seeded {chunk['strategy']}: {chunk['title']}")
    return count


def main() -> None:
    n = seed_playbook()
    print(f"Done. {n} playbook chunk(s) upserted.")


if __name__ == "__main__":
    main()
