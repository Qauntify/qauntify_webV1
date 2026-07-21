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
    assert cfg.sealion_api_keys == ("sk-test",)
    assert cfg.supabase_url == "https://abc.supabase.co"  # trailing slash stripped
    assert cfg.supabase_service_key == "service-key"
    assert cfg.symbols == ("BTCUSD", "ETHUSD", "XAUUSD", "GBPUSD")
    assert cfg.timeframe == "1h"


def test_load_config_numbered_keys_win_and_sort(monkeypatch):
    _set_all_keys(monkeypatch)
    monkeypatch.setenv("SEALION_API_KEY2", "sk-two")
    monkeypatch.setenv("SEALION_API_KEY1", "sk-one")
    monkeypatch.setenv("SEALION_API_KEY3", "  ")  # blank slots are skipped
    cfg = load_config()
    assert cfg.sealion_api_keys == ("sk-one", "sk-two")
    assert cfg.sealion_api_key == "sk-one"


def test_load_config_comma_list(monkeypatch):
    _set_all_keys(monkeypatch)
    monkeypatch.delenv("SEALION_API_KEY")
    monkeypatch.setenv("SEALION_API_KEYS", "sk-a, sk-b,,sk-c")
    cfg = load_config()
    assert cfg.sealion_api_keys == ("sk-a", "sk-b", "sk-c")
    assert cfg.sealion_api_key == "sk-a"


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
