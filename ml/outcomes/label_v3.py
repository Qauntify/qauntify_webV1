"""Vectorized, offline-only label_v3 resolver for XAUUSD M5 decisions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


POLICY_VERSION = "label_v3_1"


@dataclass(frozen=True)
class LabelV3Settings:
    atr_period: int = 14
    target_atr: float = 1.5
    stop_atr: float = 1.0
    horizon_bars: int = 48
    costs_r: tuple[float, float, float] = (0.02, 0.03, 0.05)


def load_m5_csv(path: Path, *, limit: int | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=";", nrows=limit)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if list(frame.columns) != required:
        raise ValueError(f"Unexpected M5 columns: {list(frame.columns)!r}")
    frame["timestamp"] = pd.to_datetime(frame.pop("Date"), format="%Y.%m.%d %H:%M")
    frame = frame.rename(columns=str.lower)
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("M5 timestamps must be unique and chronological")
    valid = (
        (frame["open"] > 0)
        & (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["high"] >= frame["low"])
    )
    if not bool(valid.all()):
        raise ValueError("M5 source contains invalid OHLC rows")
    return frame


def wilder_atr(frame: pd.DataFrame, period: int = 14) -> np.ndarray:
    high, low, close = (frame[name].to_numpy(dtype="float64") for name in ("high", "low", "close"))
    out = np.full(len(frame), np.nan, dtype="float64")
    if len(frame) < period + 1:
        return out
    tr = np.full(len(frame), np.nan, dtype="float64")
    tr[1:] = np.maximum.reduce((high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    previous = float(np.mean(tr[1 : period + 1]))
    out[period] = previous
    for index in range(period + 1, len(frame)):
        previous = (previous * (period - 1) + tr[index]) / period
        out[index] = previous
    return out


def _candidate_ids(timestamps: pd.Series) -> list[str]:
    return [hashlib.sha256(f"XAUUSD|M5|{value.isoformat()}|{POLICY_VERSION}".encode()).hexdigest() for value in timestamps]


def _gap_mask(timestamps: np.ndarray, horizon: int, gaps: tuple[tuple[pd.Timestamp, pd.Timestamp], ...]) -> np.ndarray:
    mask = np.zeros(len(timestamps), dtype=bool)
    valid_end = len(timestamps) - horizon
    if valid_end <= 0:
        return mask
    end_times = timestamps[horizon:]
    starts = timestamps[:valid_end]
    for gap_start, gap_resume in gaps:
        mask[:valid_end] |= (starts <= gap_start.to_datetime64()) & (end_times >= gap_resume.to_datetime64())
    return mask


def resolve_labels(
    candles: pd.DataFrame,
    settings: LabelV3Settings = LabelV3Settings(),
    *,
    material_gaps: tuple[tuple[pd.Timestamp, pd.Timestamp], ...] = (),
) -> pd.DataFrame:
    n, horizon = len(candles), settings.horizon_bars
    timestamps = candles["timestamp"].reset_index(drop=True)
    decision_timestamps = timestamps + pd.Timedelta(minutes=5)
    values = {name: candles[name].to_numpy(dtype="float64") for name in ("open", "high", "low", "close")}
    atr = wilder_atr(candles, settings.atr_period)
    result = pd.DataFrame({
        "candidate_id": _candidate_ids(decision_timestamps),
        "source_bar_open_timestamp": timestamps,
        "decision_timestamp": decision_timestamps,
        "entry_timestamp": timestamps.shift(-1),
        "entry_price": np.r_[values["open"][1:], np.nan],
        "atr_at_decision": atr,
    })
    result["policy_version"] = POLICY_VERSION
    result["right_censored"] = np.arange(n) + horizon >= n
    result["invalid_reason"] = pd.Series([None] * n, dtype="object")
    result.loc[np.isnan(atr), "invalid_reason"] = "ATR_WARMUP"
    gap_crossing = _gap_mask(timestamps.to_numpy(), horizon, material_gaps)
    result.loc[gap_crossing, "invalid_reason"] = "MATERIAL_SOURCE_GAP"

    decision_count = max(0, n - horizon)
    active = np.zeros(n, dtype=bool)
    active[:decision_count] = ~np.isnan(atr[:decision_count]) & ~gap_crossing[:decision_count]
    entry = result["entry_price"].to_numpy(dtype="float64")
    long_tp, long_sl = entry + settings.target_atr * atr, entry - settings.stop_atr * atr
    short_tp, short_sl = entry - settings.target_atr * atr, entry + settings.stop_atr * atr
    for name, array in (("long_tp_price", long_tp), ("long_sl_price", long_sl), ("short_tp_price", short_tp), ("short_sl_price", short_sl)):
        result[name] = array

    for direction in ("long", "short"):
        unresolved = active.copy()
        terminal = np.full(n, None, dtype="object")
        ambiguity = np.zeros(n, dtype=bool)
        holding = np.full(n, np.nan)
        exit_price = np.full(n, np.nan)
        exit_time = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
        mfe = np.full(n, np.nan)
        mae = np.full(n, np.nan)
        run_high = np.full(n, -np.inf)
        run_low = np.full(n, np.inf)
        tp, sl = (long_tp, long_sl) if direction == "long" else (short_tp, short_sl)
        for step in range(1, horizon + 1):
            count = n - step
            idx = np.arange(count)
            eligible = unresolved[:count]
            if not eligible.any():
                continue
            highs, lows = values["high"][step:], values["low"][step:]
            run_high[:count][eligible] = np.maximum(run_high[:count][eligible], highs[eligible])
            run_low[:count][eligible] = np.minimum(run_low[:count][eligible], lows[eligible])
            if direction == "long":
                tp_hit, sl_hit = highs >= tp[:count], lows <= sl[:count]
            else:
                tp_hit, sl_hit = lows <= tp[:count], highs >= sl[:count]
            both = eligible & tp_hit & sl_hit
            stop_only = eligible & sl_hit
            take_only = eligible & tp_hit & ~sl_hit
            for mask, state, price in ((both, "AMBIGUOUS_CONSERVATIVE_SL", sl[:count]), (stop_only & ~both, "SL", sl[:count]), (take_only, "TP", tp[:count])):
                chosen = idx[mask]
                if not len(chosen):
                    continue
                terminal[chosen] = state
                ambiguity[chosen] = state == "AMBIGUOUS_CONSERVATIVE_SL"
                holding[chosen] = step
                exit_price[chosen] = price[mask]
                exit_time[chosen] = timestamps.iloc[chosen + step].to_numpy(dtype="datetime64[ns]")
                risk = settings.stop_atr * atr[chosen]
                if direction == "long":
                    mfe[chosen] = (run_high[chosen] - entry[chosen]) / risk
                    mae[chosen] = (run_low[chosen] - entry[chosen]) / risk
                else:
                    mfe[chosen] = (entry[chosen] - run_low[chosen]) / risk
                    mae[chosen] = (entry[chosen] - run_high[chosen]) / risk
                unresolved[chosen] = False
        expired = unresolved & active
        chosen = np.flatnonzero(expired)
        if len(chosen):
            terminal[chosen] = "EXPIRED"
            holding[chosen] = horizon
            exit_price[chosen] = values["close"][chosen + horizon]
            exit_time[chosen] = timestamps.iloc[chosen + horizon].to_numpy(dtype="datetime64[ns]")
            risk = settings.stop_atr * atr[chosen]
            if direction == "long":
                mfe[chosen] = (run_high[chosen] - entry[chosen]) / risk
                mae[chosen] = (run_low[chosen] - entry[chosen]) / risk
            else:
                mfe[chosen] = (entry[chosen] - run_low[chosen]) / risk
                mae[chosen] = (entry[chosen] - run_high[chosen]) / risk
        gross = np.full(n, np.nan)
        resolved = np.flatnonzero(active)
        if direction == "long":
            gross[resolved] = (exit_price[resolved] - entry[resolved]) / (settings.stop_atr * atr[resolved])
        else:
            gross[resolved] = (entry[resolved] - exit_price[resolved]) / (settings.stop_atr * atr[resolved])
        result[f"{direction}_result"] = terminal
        result[f"{direction}_ambiguity_detected"] = ambiguity
        result[f"{direction}_conservative_fallback"] = ambiguity
        result[f"{direction}_holding_bars"] = holding
        result[f"{direction}_exit_price"] = exit_price
        result[f"{direction}_exit_timestamp"] = pd.to_datetime(exit_time)
        result[f"{direction}_mfe_r"] = mfe
        result[f"{direction}_mae_r"] = mae
        result[f"{direction}_gross_r"] = gross
        for label, cost in zip(("base", "higher", "stress"), settings.costs_r):
            result[f"{direction}_net_r_{label}"] = gross - cost
        result[f"{direction}_net_profitable"] = (result[f"{direction}_net_r_base"] > 0).astype("Int8").where(active)
    result["supervised_eligible"] = active
    result["decision_year"] = result["decision_timestamp"].dt.year.astype("int16")
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def export_labels(frame: pd.DataFrame, output_root: Path, *, overwrite: bool = False, contract_metadata: dict | None = None) -> dict:
    if output_root.exists() and not overwrite:
        raise FileExistsError(output_root)
    if output_root.exists():
        import shutil
        shutil.rmtree(output_root)
    dataset = output_root / "dataset"
    dataset.mkdir(parents=True)
    for year, partition in frame.groupby("decision_year", sort=True):
        destination = dataset / f"decision_year={int(year)}"
        destination.mkdir()
        partition.drop(columns=["decision_year"]).to_parquet(destination / "part-000.parquet", index=False, compression="zstd")
    files = sorted(dataset.rglob("*.parquet"))
    def counts(column: str) -> dict[str, int]:
        values = frame[column].fillna("UNRESOLVED").value_counts()
        return {str(key): int(value) for key, value in sorted(values.items(), key=lambda item: str(item[0]))}

    file_checksums = {str(path.relative_to(output_root)): file_sha256(path) for path in files}
    dataset_checksum = hashlib.sha256(json.dumps(file_checksums, sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()
    manifest = {
        "label_version": POLICY_VERSION,
        "dataset_checksum": dataset_checksum,
        "rows": len(frame),
        "unique_candidate_ids": int(frame["candidate_id"].nunique()),
        "supervised_eligible_rows": int(frame["supervised_eligible"].sum()),
        "right_censored_rows": int(frame["right_censored"].sum()),
        "invalid_rows": int(frame["invalid_reason"].notna().sum()),
        "long_results": counts("long_result"),
        "short_results": counts("short_result"),
        "file_checksums": file_checksums,
        "contract_metadata": contract_metadata or {},
    }
    (output_root / "label_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", "utf-8")
    return manifest


def build_validation_report(frame: pd.DataFrame, manifest: dict) -> dict:
    eligible = frame.loc[frame["supervised_eligible"]]
    report = {
        "label_version": POLICY_VERSION,
        "rows": len(frame),
        "unique_candidate_ids": int(frame["candidate_id"].nunique()),
        "exact_candidate_coverage": len(frame) == frame["candidate_id"].nunique(),
        "supervised_eligible_rows": int(frame["supervised_eligible"].sum()),
        "right_censored_rows": int(frame["right_censored"].sum()),
        "invalid_reasons": {str(k): int(v) for k, v in frame["invalid_reason"].fillna("NONE").value_counts().items()},
        "long_ambiguity_rows": int(frame["long_ambiguity_detected"].sum()),
        "short_ambiguity_rows": int(frame["short_ambiguity_detected"].sum()),
        "either_direction_ambiguity_rows": int((frame["long_ambiguity_detected"] | frame["short_ambiguity_detected"]).sum()),
        "both_direction_ambiguity_rows": int((frame["long_ambiguity_detected"] & frame["short_ambiguity_detected"]).sum()),
        "results": {"long": manifest["long_results"], "short": manifest["short_results"]},
        "targets": {},
        "rows_by_year": {str(k): int(v) for k, v in frame["decision_year"].value_counts().sort_index().items()},
        "file_checksums": manifest["file_checksums"],
    }
    for direction in ("long", "short"):
        report["targets"][direction] = {
            "positive_rate_base": float(eligible[f"{direction}_net_profitable"].mean()),
            "mean_gross_r": float(eligible[f"{direction}_gross_r"].mean()),
            "mean_net_r_base": float(eligible[f"{direction}_net_r_base"].mean()),
            "mean_net_r_higher": float(eligible[f"{direction}_net_r_higher"].mean()),
            "mean_net_r_stress": float(eligible[f"{direction}_net_r_stress"].mean()),
            "mean_mfe_r": float(eligible[f"{direction}_mfe_r"].mean()),
            "mean_mae_r": float(eligible[f"{direction}_mae_r"].mean()),
        }
    return report


def write_validation_reports(report: dict, report_root: Path) -> tuple[Path, Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = report_root / "label_v3_1.json", report_root / "label_v3_1.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")
    lines = [
        "# label_v3 Validation", "",
        f"- Rows: `{report['rows']}`",
        f"- Unique candidate IDs: `{report['unique_candidate_ids']}`",
        f"- Exact coverage: `{report['exact_candidate_coverage']}`",
        f"- Supervised eligible: `{report['supervised_eligible_rows']}`",
        f"- Right censored: `{report['right_censored_rows']}`",
        f"- Invalid reasons: `{report['invalid_reasons']}`", "",
        "MFE and MAE include the full OHLC range of the terminal candle because intrabar ordering is unavailable.", "",
        "## Ambiguity", "",
        f"- Long ambiguity: `{report['long_ambiguity_rows']}`",
        f"- Short ambiguity: `{report['short_ambiguity_rows']}`",
        f"- Either direction: `{report['either_direction_ambiguity_rows']}`",
        f"- Both directions: `{report['both_direction_ambiguity_rows']}`", "",
        "The directional counts overlap when the same candidate is ambiguous for both directions.", "",
        "## Target summary", "",
    ]
    for direction, values in report["targets"].items():
        lines += [f"### {direction.upper()}", "", *[f"- {key}: `{value:.8f}`" for key, value in values.items()], ""]
    markdown_path.write_text("\n".join(lines), "utf-8")
    return json_path, markdown_path
