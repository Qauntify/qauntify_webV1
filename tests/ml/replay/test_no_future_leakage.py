import ml.replay.replay_engine as engine
from ml.replay.replay_engine import replay_candles


def test_appending_future_candles_does_not_change_prior_candidates(
    monkeypatch, candle_frame, strategy_config, source_manifest, long_setup,
):
    seen_lengths = []
    def detector(*args, **kwargs):
        history = args[2]
        seen_lengths.append(len(history))
        return long_setup if len(history) == 15 else None
    monkeypatch.setattr(engine, "evaluate_strategy", detector)
    boundary = 30
    before = replay_candles(
        candle_frame.iloc[:boundary], strategy=strategy_config,
        manifest=source_manifest, replay_config_version="replay_v1",
    )
    after = replay_candles(
        candle_frame, strategy=strategy_config,
        manifest=source_manifest, replay_config_version="replay_v1",
    )
    assert [row.to_dict() for row in before.candidates] == [
        row.to_dict() for row in after.candidates
        if row.source_candle_timestamp <= candle_frame.iloc[boundary - 1].timestamp.isoformat()
    ]
    assert max(seen_lengths) <= len(candle_frame)
    assert all(c.candidate_timestamp >= c.source_candle_timestamp for c in after.candidates)


def test_selected_end_is_identical_to_physically_truncated_data(
    monkeypatch, candle_frame, strategy_config, source_manifest, short_setup,
):
    monkeypatch.setattr(
        engine, "evaluate_strategy",
        lambda *args, **kwargs: short_setup if len(args[2]) == 20 else None,
    )
    selected = candle_frame[candle_frame.timestamp <= candle_frame.iloc[39].timestamp]
    first = replay_candles(
        selected, strategy=strategy_config, manifest=source_manifest,
        replay_config_version="replay_v1",
    )
    second = replay_candles(
        candle_frame.iloc[:40], strategy=strategy_config, manifest=source_manifest,
        replay_config_version="replay_v1",
    )
    assert first.candidates == second.candidates

