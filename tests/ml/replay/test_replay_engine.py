import pytest

import ml.replay.replay_engine as engine
from ml.replay.replay_engine import (
    ReplayConfig,
    ReplayConfigurationError,
    load_candles,
    replay_candles,
)


def test_empty_and_insufficient_history(candle_frame, strategy_config, source_manifest):
    empty = replay_candles(
        candle_frame.iloc[:0], strategy=strategy_config,
        manifest=source_manifest, replay_config_version="replay_v1",
    )
    assert empty.candidates == ()
    result = replay_candles(
        candle_frame.iloc[:5], strategy=strategy_config,
        manifest=source_manifest, replay_config_version="replay_v1",
    )
    assert result.stats.insufficient_history_occurrences == 5


def test_one_candidate_and_no_signal_period(
    monkeypatch, candle_frame, strategy_config, source_manifest, long_setup,
):
    monkeypatch.setattr(
        engine, "evaluate_strategy",
        lambda *args, **kwargs: long_setup if len(args[2]) == 12 else None,
    )
    result = replay_candles(
        candle_frame.iloc[:20], strategy=strategy_config,
        manifest=source_manifest, replay_config_version="replay_v1",
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].source_candle_timestamp == candle_frame.iloc[11].timestamp.isoformat()


def test_unsorted_and_duplicate_candles_fail(candle_frame, strategy_config, source_manifest):
    with pytest.raises(ReplayConfigurationError, match="not ordered"):
        replay_candles(
            candle_frame.iloc[::-1], strategy=strategy_config,
            manifest=source_manifest, replay_config_version="replay_v1",
        )
    duplicated = __import__("pandas").concat([candle_frame.iloc[:10], candle_frame.iloc[[9]]])
    with pytest.raises(ReplayConfigurationError, match="Duplicate"):
        replay_candles(
            duplicated, strategy=strategy_config,
            manifest=source_manifest, replay_config_version="replay_v1",
        )


def test_partition_read_prunes_selected_date_range(
    tmp_path, candle_frame, strategy_config,
):
    pytest.importorskip("pyarrow")
    root = tmp_path / "cleaned"
    partition = root / "symbol=XAUUSD" / "timeframe=M5" / "year=2024"
    partition.mkdir(parents=True)
    candle_frame.drop(columns=["symbol", "timeframe"]).to_parquet(
        partition / "part-0.parquet", index=False,
    )
    config = ReplayConfig(
        version="replay_v1", cleaned_dataset_root=root,
        manifest_path=root / "dataset_manifest.json",
        candidates_root=tmp_path / "candidates", reports_root=tmp_path / "reports",
        symbols=("XAUUSD",), strategies=(strategy_config,),
        closed_candles_only=True, fail_on_invalid_candidate=True,
        fail_on_duplicate_candidate_id=True,
        partition_columns=("symbol", "timeframe", "strategy_name", "year"),
        compression="zstd",
    )
    selected = load_candles(
        config, symbol="XAUUSD", timeframe="M5",
        start=candle_frame.iloc[10].timestamp,
        end=candle_frame.iloc[19].timestamp,
    )
    assert len(selected) == 10
    assert selected.timestamp.min() == candle_frame.iloc[10].timestamp

    with pytest.raises(ReplayConfigurationError, match="partition is missing"):
        load_candles(config, symbol="XAUUSD", timeframe="H1")


def test_partition_fragments_are_sorted_before_limit(
    tmp_path, candle_frame, strategy_config,
):
    pytest.importorskip("pyarrow")
    root = tmp_path / "cleaned"
    partition = root / "symbol=XAUUSD" / "timeframe=M5" / "year=2024"
    partition.mkdir(parents=True)
    columns = [column for column in candle_frame if column not in {"symbol", "timeframe"}]
    candle_frame.iloc[40:].loc[:, columns].to_parquet(partition / "a-later.parquet", index=False)
    candle_frame.iloc[:40].loc[:, columns].to_parquet(partition / "z-earlier.parquet", index=False)
    config = ReplayConfig(
        version="replay_v1", cleaned_dataset_root=root,
        manifest_path=root / "dataset_manifest.json",
        candidates_root=tmp_path / "candidates", reports_root=tmp_path / "reports",
        symbols=("XAUUSD",), strategies=(strategy_config,),
        closed_candles_only=True, fail_on_invalid_candidate=True,
        fail_on_duplicate_candidate_id=True,
        partition_columns=("symbol", "timeframe", "strategy_name", "year"),
        compression="zstd",
    )
    selected = load_candles(config, symbol="XAUUSD", timeframe="M5", limit=10)
    assert selected.timestamp.is_monotonic_increasing
    assert selected.timestamp.tolist() == candle_frame.timestamp.iloc[:10].tolist()
