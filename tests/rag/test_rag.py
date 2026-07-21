"""Tests for hybrid RAG formatting and retrieval soft-fail."""
from signals.models import CandidateSetup
from signals.rag.format import format_rag_block
from signals.rag.playbook import PLAYBOOK_CHUNKS
from signals.rag.retrieve import local_playbook_chunks, retrieve_context
from signals.composer import build_messages, confirm_setup


SETUP = CandidateSetup(
    symbol="BTCUSDT",
    direction="long",
    entry=100.0,
    stop_loss=98.0,
    take_profit=104.0,
    indicators={"strategy": "ict_fvg", "atr": 1.2},
)


def test_format_rag_block_joins_sections():
    block = format_rag_block(
        outcomes=[{
            "status": "tp3_hit", "direction": "long", "entry": 100,
            "confidence": 70, "closed_at": "2026-07-01T00:00:00Z",
            "indicators": {"strategy": "ict_fvg"},
        }],
        rationales=[{
            "kind": "confirm", "confidence": 72,
            "rationale": "Sweep and FVG retest aligned with London session.",
        }],
        playbook=[{"title": "5m ICT FVG confirm gate", "body": "Need sweep + CHoCH + FVG."}],
    )
    assert "Retrieved context" in block
    assert "tp3_hit" in block
    assert "confirm conf=72" in block
    assert "Playbook" in block


def test_format_rag_block_empty_is_blank():
    assert format_rag_block() == ""
    assert format_rag_block(outcomes=[], rationales=[], playbook=[]) == ""


def test_local_playbook_filters_by_strategy():
    chunks = local_playbook_chunks("ict_fvg", "long confirm FVG retest")
    assert chunks
    assert all(c["strategy"] == "ict_fvg" for c in chunks)
    assert len(chunks) <= 2
    assert "confirm" in chunks[0]["title"].lower()


def test_local_playbook_prefers_confirm_gate_over_reject_cues():
    chunks = local_playbook_chunks("ict_fvg", "ict_fvg 5m long confirm risk reward")
    assert chunks
    assert "confirm" in chunks[0]["title"].lower()


def test_retrieve_context_soft_fails_and_uses_local_playbook(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "signals.rag.retrieve.fetch_similar_outcomes", boom,
    )
    monkeypatch.setattr(
        "signals.rag.retrieve.fetch_similar_rationales", boom,
    )
    monkeypatch.setattr(
        "signals.rag.retrieve.match_playbook_chunks", boom,
    )

    class NoEmbed:
        pass

    block = retrieve_context(
        SETUP,
        strategy="ict_fvg",
        timeframe="5m",
        supabase_url="https://example.supabase.co",
        service_key="service",
        llm=NoEmbed(),
    )
    assert "Playbook" in block
    assert "ict" in block.lower() or "FVG" in block


def test_build_messages_includes_rag_block():
    messages = build_messages(
        SETUP, strategy="ict_fvg", timeframe="5m",
        rag_block="Retrieved context:\n- sample",
    )
    assert "Retrieved context" in messages[1]["content"]
    assert "sample" in messages[1]["content"]
    assert "retrieved context" in messages[0]["content"].lower()


def test_confirm_setup_passes_rag_into_llm():
    class FakeLLM:
        def __init__(self):
            self.last_messages = None

        def chat(self, messages, temperature=0.2):
            self.last_messages = messages
            return '{"verdict":"confirm","confidence":80,"rationale":"ok"}'

    llm = FakeLLM()
    result = confirm_setup(
        SETUP, llm, strategy="ict_fvg", timeframe="5m",
        rag_block="Retrieved context:\n- past win",
    )
    assert result.verdict == "confirm"
    assert "past win" in llm.last_messages[1]["content"]


def test_playbook_covers_all_strategies():
    strategies = {c["strategy"] for c in PLAYBOOK_CHUNKS}
    assert strategies >= {"ict_fvg", "ce_lwma", "ict_smc", "ema_cross"}
