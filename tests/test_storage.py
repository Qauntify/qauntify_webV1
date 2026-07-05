import json
import sqlite3

from signals.models import CandidateSetup, Confirmation, make_signal
from signals.storage import save_signal


def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])


def test_save_signal_writes_sqlite_row(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    signal = _signal()
    save_signal(signal, db_path=db, json_path=js)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM signals").fetchone()
    conn.close()
    assert row["id"] == signal.id
    assert row["symbol"] == "BTCUSDT"
    assert row["direction"] == "long"
    assert row["entry"] == 100.0
    assert row["confidence"] == 80
    assert json.loads(row["indicators"])["rsi"] == 55.0
    assert json.loads(row["news_headlines"]) == ["headline one"]


def test_save_signal_appends_to_json(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    first = _signal()
    second = _signal()
    save_signal(first, db_path=db, json_path=js)
    save_signal(second, db_path=db, json_path=js)

    with open(js) as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["id"] == first.id
    assert data[1]["id"] == second.id
    assert data[0]["news_headlines"] == ["headline one"]


def test_save_signal_creates_table_if_missing(tmp_path):
    db = str(tmp_path / "fresh.db")
    js = str(tmp_path / "fresh.json")
    save_signal(_signal(), db_path=db, json_path=js)
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 1


def test_save_signal_recovers_from_corrupt_json(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    with open(js, "w") as f:
        f.write("")  # simulate truncated/corrupt mirror file
    signal = _signal()
    save_signal(signal, db_path=db, json_path=js)
    with open(js) as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["id"] == signal.id


def test_save_signal_recovers_from_non_list_json(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    with open(js, "w") as f:
        f.write('{"not": "a list"}')
    save_signal(_signal(), db_path=db, json_path=js)
    with open(js) as f:
        data = json.load(f)
    assert len(data) == 1
