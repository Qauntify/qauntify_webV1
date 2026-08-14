"""Detects when 2+ independent strategies are simultaneously open on the
same symbol + direction, and publishes a distinct 'confluence' signal.

The caller (engine.main()) wraps the single call into this module in
try/except -- a confluence-detection failure must never block the three
real sessions' own signal delivery, which has already completed by the
time this runs.
"""
from signals.chart.pipeline import attach_chart
from signals.models import CandidateSetup, Confirmation, Signal, make_signal
from signals.persistence.signals import (
    has_open_confluence_signal,
    open_signals_same_direction,
    save_signal,
)
from signals.pipeline.deliver import maybe_send_alert

CONFLUENCE_TIMEFRAME = "confluence"


def _build_confluence_signal(signal: Signal, other: dict) -> Signal:
    """A new Signal reusing `signal`'s own levels, tagged with both
    contributing strategies. `other` is one row from
    `open_signals_same_direction` (has `timeframe` and `indicators`)."""
    strategy = signal.indicators.get("strategy", "unknown")
    other_strategy = (other.get("indicators") or {}).get("strategy", "unknown")
    tag_new = f"{strategy}@{signal.timeframe}"
    tag_other = f"{other_strategy}@{other.get('timeframe', 'unknown')}"

    indicators = dict(signal.indicators)
    indicators["confluence_of"] = [tag_new, tag_other]
    # Outcome tracking needs the real interval -- "confluence" itself is not
    # a fetchable broker interval. See track_open_signals in
    # signals/outcomes/tracker.py.
    indicators["source_timeframe"] = signal.timeframe

    setup = CandidateSetup(
        symbol=signal.symbol, direction=signal.direction, entry=signal.entry,
        stop_loss=signal.stop_loss, take_profit=signal.take_profit,
        take_profit_2=signal.take_profit_2, take_profit_3=signal.take_profit_3,
        indicators=indicators,
    )
    rationale = (
        f"{tag_new} confirms {signal.direction}, agreeing with an "
        f"already-open {tag_other} {signal.direction} — confluence signal."
    )
    confirmation = Confirmation("confirm", signal.confidence, rationale)
    return make_signal(setup, confirmation, [], timeframe=CONFLUENCE_TIMEFRAME)


def detect_confluence(newly_confirmed: list, candles_by_symbol: dict,
                      settings, cfg, session=None) -> list:
    """For each signal confirmed this run, check whether a different
    strategy is already open on the same symbol+direction; if so, and no
    confluence signal is already open for that symbol, publish one.

    Returns the list of confluence Signal objects published this run, so the
    caller can fold them into the run summary.
    """
    published = []
    for signal in newly_confirmed:
        try:
            strategy = signal.indicators.get("strategy")
            if not strategy:
                continue
            others = open_signals_same_direction(
                signal.symbol, signal.direction, exclude_strategy=strategy,
                supabase_url=cfg.supabase_url,
                service_key=cfg.supabase_service_key, session=session,
            )
            if not others:
                continue
            if has_open_confluence_signal(
                signal.symbol, cfg.supabase_url, cfg.supabase_service_key,
                session=session,
            ):
                continue

            confluence = _build_confluence_signal(signal, others[0])
            candles = candles_by_symbol.get((signal.symbol, signal.timeframe))
            if candles:
                confluence = attach_chart(
                    confluence, candles,
                    supabase_url=cfg.supabase_url,
                    service_key=cfg.supabase_service_key, session=session,
                )
            save_signal(confluence, cfg.supabase_url, cfg.supabase_service_key,
                        session=session)
            maybe_send_alert(confluence, settings, cfg)
            published.append(confluence)
        except Exception as exc:
            # Each signal's confluence check is independent -- one failure
            # (e.g. a transient Supabase error) must not skip the rest of
            # this cycle's batch. The engine-level try/except around the
            # whole detect_confluence() call only protects the three real
            # sessions' own delivery, not sibling signals within this loop.
            print(f"[{signal.symbol}] confluence check failed "
                  f"({type(exc).__name__}), continuing")
    return published
