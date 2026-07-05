import pytest

from signals.config import Config, load_config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    monkeypatch.setenv("CRYPTOPANIC_API_KEY", "cp-test")
    cfg = load_config()
    assert cfg.sealion_api_key == "sk-test"
    assert cfg.cryptopanic_api_key == "cp-test"
    assert cfg.symbols == ("BTCUSDT", "ETHUSDT")
    assert cfg.timeframe == "1h"


def test_load_config_missing_sealion_key_exits(monkeypatch):
    monkeypatch.delenv("SEALION_API_KEY", raising=False)
    monkeypatch.setenv("CRYPTOPANIC_API_KEY", "cp-test")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_missing_cryptopanic_key_exits(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    monkeypatch.delenv("CRYPTOPANIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()
