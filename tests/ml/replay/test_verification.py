from ml.replay.replay_engine import StrategyConfig
from ml.replay.verification import verify_production_parity


def test_production_parity_helper_compares_identical_router_inputs(candle_frame):
    result = verify_production_parity(
        candle_frame,
        StrategyConfig("ema_cross", "M5", None, 20),
    )
    assert result.evaluations == 61
    assert result.mismatches == 0
