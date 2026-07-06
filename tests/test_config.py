import pytest

from signals.config import Config, load_config


@pytest.fixture(autouse=True)
def isolate_from_real_dotenv(monkeypatch):
    """Stub load_dotenv so a developer's real .env can't leak keys into the
    missing-key tests (find_dotenv walks up from the source tree, not cwd)."""
    monkeypatch.setattr("signals.config.load_dotenv", lambda: None)


def _set_all_keys(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")


def test_load_config_reads_env(monkeypatch):
    _set_all_keys(monkeypatch)
    cfg = load_config()
    assert cfg.sealion_api_key == "sk-test"
    assert cfg.supabase_url == "https://abc.supabase.co"  # trailing slash stripped
    assert cfg.supabase_service_key == "service-key"
    assert cfg.symbols == ("BTCUSDT", "ETHUSDT")
    assert cfg.timeframe == "1h"


@pytest.mark.parametrize("missing", [
    "SEALION_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
])
def test_load_config_missing_key_exits(monkeypatch, missing):
    _set_all_keys(monkeypatch)
    monkeypatch.delenv(missing)
    with pytest.raises(SystemExit):
        load_config()
