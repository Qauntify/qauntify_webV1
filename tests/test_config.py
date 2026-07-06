import pytest

from signals.config import Config, load_config


@pytest.fixture(autouse=True)
def isolate_from_real_dotenv(monkeypatch):
    """Stub load_dotenv so a developer's real .env can't leak keys into the
    missing-key tests (find_dotenv walks up from the source tree, not cwd)."""
    monkeypatch.setattr("signals.config.load_dotenv", lambda: None)


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    cfg = load_config()
    assert cfg.sealion_api_key == "sk-test"
    assert cfg.symbols == ("BTCUSDT", "ETHUSDT")
    assert cfg.timeframe == "1h"


def test_load_config_missing_sealion_key_exits(monkeypatch):
    monkeypatch.delenv("SEALION_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()
