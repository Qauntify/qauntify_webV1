"""Session opening-range anchors, range slicing, and relative volume.

Split from detector.py because this arithmetic — locating an anchor's trade
window, slicing its opening range, and averaging same-anchor volume history —
is the fiddly part and is worth testing independently of the entry/stop/TP
rules built on top of it. See
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.

Anchors are matched against each bar's own open_time (UTC wall clock), not
counted forward from the start of `candles` — so behaviour does not shift if
the caller passes a differently-sized window (the live engine's rolling
candle_limit slice vs. a full backtest history).
"""

# (hour, minute, name), UTC. All three land on 15m boundaries.
SESSION_ANCHORS_UTC = ((0, 0, "Asia"), (7, 0, "London"), (13, 30, "NY"))

OR_BARS = 2  # 15m bars forming the opening range (30 minutes)
TRADE_WINDOW_BARS = 16  # bars after the OR closes in which a breakout may trigger
RVOL_LOOKBACK = 10  # prior same-anchor opens averaged
MIN_RVOL_SAMPLES = 3  # minimum priors before RVOL is trusted

_BAR_MS = 15 * 60_000
_DAY_MS = 24 * 60 * 60_000
_ANCHOR_MS = tuple((name, (h * 60 + m) * 60_000) for h, m, name in SESSION_ANCHORS_UTC)
_WINDOW_END_MS = (OR_BARS + TRADE_WINDOW_BARS) * _BAR_MS


def _anchor_indices(candles):
    """[(index, anchor_name), ...] for every bar whose open_time lands
    exactly on a session anchor, oldest first."""
    hits = []
    for i, c in enumerate(candles):
        ms_of_day = c.open_time % _DAY_MS
        for name, anchor_ms in _ANCHOR_MS:
            if ms_of_day == anchor_ms:
                hits.append((i, name))
                break
    return hits


def current_anchor(candles):
    """(anchor_name, anchor_index) whose trade window contains the LAST bar
    in `candles`, or (None, None) if it falls in no anchor's window.

    `anchor_index` is where the anchor's own bar sits in `candles` — the
    opening range is `candles[anchor_index : anchor_index + OR_BARS]`.
    """
    if not candles:
        return None, None
    last = candles[-1]
    idx, name = None, None
    for i, n in _anchor_indices(candles):
        if candles[i].open_time <= last.open_time:
            idx, name = i, n
    if idx is None:
        return None, None
    if last.open_time - candles[idx].open_time >= _WINDOW_END_MS:
        return None, None
    return name, idx


def opening_range(candles, anchor_index):
    """(or_high, or_low, or_direction) for the OR starting at `anchor_index`,
    or None if fewer than OR_BARS bars are available there.

    `or_direction` is "bullish" (the OR's last close is above its first
    open), "bearish" (below), or None for a doji (equal).
    """
    bars = candles[anchor_index:anchor_index + OR_BARS]
    if len(bars) < OR_BARS:
        return None
    or_high = max(b.high for b in bars)
    or_low = min(b.low for b in bars)
    if bars[-1].close > bars[0].open:
        direction = "bullish"
    elif bars[-1].close < bars[0].open:
        direction = "bearish"
    else:
        direction = None
    return or_high, or_low, direction


def opening_range_volume(candles, anchor_index):
    """Summed volume of the OR_BARS opening-range bars, or None if
    incomplete."""
    bars = candles[anchor_index:anchor_index + OR_BARS]
    if len(bars) < OR_BARS:
        return None
    return sum(b.volume for b in bars)


def relative_volume(candles, anchor_name, anchor_index):
    """current OR volume / mean OR volume of the previous RVOL_LOOKBACK
    same-`anchor_name` occurrences (zero-volume ones excluded), or None if
    fewer than MIN_RVOL_SAMPLES qualify, or the current OR volume is 0.

    Comparing against the SAME anchor's history (not a rolling average
    across all anchors) is a necessary adaptation, not a stylistic one:
    volume at 13:30 UTC is structurally many times volume at 00:00 UTC, so a
    rolling mean would flag every NY open as "abnormal" and every Asia open
    as "quiet" — measuring time-of-day seasonality, not the catalyst this
    strategy is trying to detect.
    """
    current = opening_range_volume(candles, anchor_index)
    if not current:  # None (incomplete) or 0.0
        return None
    priors = [
        v for i, name in _anchor_indices(candles[:anchor_index])
        if name == anchor_name
        for v in [opening_range_volume(candles, i)]
        if v
    ][-RVOL_LOOKBACK:]
    if len(priors) < MIN_RVOL_SAMPLES:
        return None
    return current / (sum(priors) / len(priors))
