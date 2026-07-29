"""Strict, side-effect-free validation for Milestone 1 v3 configuration files."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_ROOT = PROJECT_ROOT / "ml" / "configs"


class V3ConfigurationError(ValueError):
    """Raised when a v3 contract is missing, unsafe, or inconsistent."""


@dataclass(frozen=True)
class V3ConfigBundle:
    experiment: Mapping[str, Any]
    label: Mapping[str, Any]
    cost: Mapping[str, Any]
    split: Mapping[str, Any]
    safeguards: Mapping[str, Any]
    checksums: Mapping[str, str]
    ready_for_label_implementation: bool
    ready_for_policy_optimization: bool


CONFIG_PATHS = {
    "experiment": Path("experiments/xauusd_m5_directional_v1.yaml"),
    "label": Path("labels/label_v3.yaml"),
    "cost": Path("costs/xauusd_cost_v3.yaml"),
    "split": Path("splits/xauusd_m5_split_v3.yaml"),
    "safeguards": Path("policies/policy_safeguards_v3.yaml"),
}


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency error is explicit
        raise V3ConfigurationError("PyYAML is required to validate v3 configs") from exc
    if not path.is_file():
        raise V3ConfigurationError(f"Missing v3 configuration: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise V3ConfigurationError(f"Configuration must be a mapping: {path}")
    return raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise V3ConfigurationError(message)


def _dt(value: Any, field: str) -> datetime:
    _require(isinstance(value, str) and value.strip() != "", f"{field} must be a timestamp string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V3ConfigurationError(f"{field} is not an ISO timestamp: {value!r}") from exc


def _canonical_checksum(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_experiment(raw: Mapping[str, Any]) -> None:
    _require(raw.get("version") == "experiment_v3", "experiment version must be experiment_v3")
    _require(raw.get("experiment_id") == "xauusd_m5_directional_v1", "unexpected experiment_id")
    _require(raw.get("instrument") == "XAUUSD", "experiment instrument must be XAUUSD")
    _require(raw.get("decision_timeframe") == "M5", "decision timeframe must be M5")
    _require(raw.get("context_timeframes") == ["M15"], "M15 must be the only context timeframe")
    _require(raw.get("use_m1_data") is False, "M1 data must be disabled")
    _require(raw.get("candidate_frequency_bars") == 1, "candidate frequency must be every M5 bar")
    _require(raw.get("allow_overlapping_label_candidates") is True, "overlapping label candidates must be explicit")
    _require(raw.get("live_trading_changes_authorized") is False, "live trading changes must remain unauthorized")
    inputs = raw.get("input", {})
    _require(set(inputs) == {"M5", "M15", "replacement_report"}, "experiment inputs must be M5, M15, and replacement_report")
    for name, value in inputs.items():
        path = (PROJECT_ROOT / str(value)).resolve()
        _require(path.is_file(), f"configured {name} input does not exist: {path}")
    interval = raw.get("eligible_interval", {})
    _require(_dt(interval.get("start_inclusive"), "eligible start") < _dt(interval.get("end_exclusive"), "eligible end"), "eligible interval is empty")


def _validate_label(raw: Mapping[str, Any]) -> None:
    _require(raw.get("version") == "label_v3", "label version must be label_v3")
    _require(raw.get("decision_timeframe") == "M5", "label decision timeframe must be M5")
    _require(raw.get("context_timeframes") == ["M15"], "label context must be M15 only")
    _require(raw.get("entry", {}).get("policy") == "next_bar_open", "entry must use next_bar_open")
    _require(raw.get("atr", {}).get("source_bar") == "decision_bar", "ATR must use the decision bar")
    _require(raw.get("atr", {}).get("freeze_after_entry") is True, "ATR must remain frozen")
    barriers = raw.get("barriers", {})
    _require(float(barriers.get("target_atr", 0)) == 1.5, "target barrier must be 1.5 ATR")
    _require(float(barriers.get("stop_atr", 0)) == 1.0, "stop barrier must be 1.0 ATR")
    _require(int(barriers.get("horizon_bars", 0)) == 48, "outcome horizon must be 48 M5 bars")
    _require(int(barriers.get("scan_last_bar_offset", 0)) == 48, "last scan offset must be 48")
    ambiguity = raw.get("ambiguity", {})
    _require(ambiguity.get("use_lower_timeframe") is False, "lower-timeframe ambiguity resolution must be disabled")
    _require(ambiguity.get("same_m5_candle_policy") == "stop_first_conservative", "same-M5 ambiguity must resolve SL first")
    targets = raw.get("targets", {})
    _require(targets.get("long_binary", {}).get("name") == "long_net_profitable", "invalid long target")
    _require(targets.get("short_binary", {}).get("name") == "short_net_profitable", "invalid short target")
    _require(raw.get("candidate_records_mutable") is False, "candidate records must remain immutable")


def _validate_cost(raw: Mapping[str, Any]) -> None:
    _require(raw.get("version") == "xauusd_cost_v3", "cost version must be xauusd_cost_v3")
    _require(raw.get("unit") == "R", "cost unit must be R")
    _require(raw.get("model") == "all_in_round_trip_proxy", "cost model must be the all-in proxy")
    scenarios = raw.get("scenarios", {})
    expected = {"base": (0.02, True), "higher": (0.03, True), "stress": (0.05, False)}
    _require(set(scenarios) == set(expected), "cost scenarios must be base, higher, and stress")
    for name, (cost, hard) in expected.items():
        _require(float(scenarios[name].get("total_round_trip_cost_r", -1)) == cost, f"unexpected {name} cost")
        _require(scenarios[name].get("hard_pass_required") is hard, f"unexpected {name} hard-pass rule")
    _require(raw.get("subtract_component_costs_in_addition_to_proxy") is False, "component costs must not be double-counted")


def _validate_splits(raw: Mapping[str, Any]) -> None:
    _require(raw.get("version") == "xauusd_m5_split_v3", "split version must be xauusd_m5_split_v3")
    _require(raw.get("approval_status") in {"proposed_requires_approval", "approved"}, "invalid split approval status")
    _require(raw.get("interval_semantics") == "half_open", "split intervals must be half-open")
    eligible = raw.get("eligible_interval", {})
    eligible_start = _dt(eligible.get("start_inclusive"), "split eligible start")
    eligible_end = _dt(eligible.get("end_exclusive"), "split eligible end")
    split = raw.get("chronological_split", {})
    train_start, train_end = _dt(split.get("train", {}).get("start_inclusive"), "train start"), _dt(split.get("train", {}).get("end_exclusive"), "train end")
    validation_start, validation_end = _dt(split.get("validation", {}).get("start_inclusive"), "validation start"), _dt(split.get("validation", {}).get("end_exclusive"), "validation end")
    test = split.get("untouched_test", {})
    test_start, test_end = _dt(test.get("start_inclusive"), "test start"), _dt(test.get("end_exclusive"), "test end")
    _require((eligible_start, eligible_end) == (train_start, test_end), "splits must cover the eligible interval")
    _require(train_end == validation_start and validation_end == test_start, "train, validation, and test must be contiguous")
    _require(train_start < train_end < validation_end < test_end, "split chronology is invalid")
    _require(test.get("locked") is True, "untouched test must be locked")
    protection = raw.get("protection", {})
    horizon = int(protection.get("outcome_horizon_bars", 0))
    minutes = int(protection.get("bar_minutes", 0))
    _require((horizon, minutes) == (48, 5), "split protection must use 48 M5 bars")
    _require(int(protection.get("purge_minutes", 0)) == horizon * minutes, "purge must cover the 4-hour horizon")
    _require(int(protection.get("embargo_minutes", 0)) == horizon * minutes, "embargo must cover the 4-hour horizon")
    _require(protection.get("purge_by_outcome_exit_timestamp") is True, "purging must use outcome exit timestamps")
    definitions = raw.get("walk_forward", {}).get("definitions", [])
    _require(raw.get("walk_forward", {}).get("folds") == 5 and len(definitions) == 5, "exactly five folds are required")
    previous_validation_end = None
    for expected_fold, fold in enumerate(definitions, start=1):
        _require(fold.get("fold") == expected_fold, "fold IDs must be 1 through 5")
        fold_train_start = _dt(fold.get("train_start_inclusive"), f"fold {expected_fold} train start")
        fold_train_end = _dt(fold.get("train_end_exclusive"), f"fold {expected_fold} train end")
        fold_validation_start = _dt(fold.get("validation_start_inclusive"), f"fold {expected_fold} validation start")
        fold_validation_end = _dt(fold.get("validation_end_exclusive"), f"fold {expected_fold} validation end")
        _require(fold_train_start == eligible_start, "walk-forward training must use an expanding window")
        _require(fold_train_end == fold_validation_start, "fold train and validation boundary must be contiguous before purging")
        _require(fold_train_start < fold_train_end < fold_validation_end <= test_start, "fold chronology reaches or crosses test")
        if previous_validation_end is not None:
            _require(fold_validation_start == previous_validation_end, "walk-forward validation windows must be contiguous")
        previous_validation_end = fold_validation_end
    access = raw.get("test_access", {})
    _require(all(access.get(key) is True for key in ("cli_locked_by_default", "approval_artifact_required", "frozen_policy_manifest_required", "matching_checksums_required", "access_log_required")), "all test locks are required")
    _require(access.get("maximum_policy_evaluations") == 1, "test policy may be evaluated only once")


def _validate_safeguards(raw: Mapping[str, Any]) -> None:
    _require(raw.get("version") == "policy_safeguards_v3", "safeguard version must be policy_safeguards_v3")
    _require(raw.get("approval_status") in {"proposed_requires_approval", "approved"}, "invalid safeguard approval status")
    folds, coverage = raw.get("folds", {}), raw.get("coverage", {})
    _require(folds.get("total") == 5 and folds.get("minimum_positive") == 4, "four of five positive folds are required")
    _require(folds.get("reject_zero_trade_folds") is True, "zero-trade folds must be rejected")
    _require(float(coverage.get("minimum", 0)) == 0.05, "minimum coverage must be 5%")
    per_fold = int(coverage.get("minimum_accepted_candidates_per_fold", 0))
    total = int(coverage.get("minimum_total_accepted_candidates", 0))
    _require(per_fold == 100, "minimum accepted candidates per fold must be 100")
    _require(total >= per_fold * 5, "minimum total candidates cannot be below the fold minimum total")
    economics = raw.get("economics", {})
    _require(float(economics.get("maximum_execution_constrained_drawdown_r", 0)) > 0, "maximum drawdown must be positive")
    concentration = raw.get("concentration", {})
    for key in ("maximum_single_fold_positive_profit_share", "maximum_single_year_positive_profit_share"):
        value = float(concentration.get(key, 0))
        _require(0 < value < 1, f"{key} must be between zero and one")
    execution = raw.get("execution", {})
    _require(execution.get("maximum_open_positions") == 1, "only one open position is allowed")
    _require(execution.get("same_timestamp_long_short_conflict") == "NO_TRADE", "same-time conflict must be NO_TRADE")
    selection = raw.get("selection", {})
    _require(selection.get("reject_if_any_hard_safeguard_fails") is True, "hard safeguards must be mandatory")
    _require(selection.get("maximum_locked_policies") == 1, "at most one policy may be locked")
    _require(selection.get("untouched_test_used_for_selection") is False, "test cannot be used for selection")


def load_and_validate_v3_configs(config_root: Path = DEFAULT_CONFIG_ROOT) -> V3ConfigBundle:
    root = Path(config_root).resolve()
    configs = {name: _load_yaml(root / relative) for name, relative in CONFIG_PATHS.items()}
    _validate_experiment(configs["experiment"])
    _validate_label(configs["label"])
    _validate_cost(configs["cost"])
    _validate_splits(configs["split"])
    _validate_safeguards(configs["safeguards"])
    experiment_interval = configs["experiment"]["eligible_interval"]
    split_interval = configs["split"]["eligible_interval"]
    _require(experiment_interval["start_inclusive"] == split_interval["start_inclusive"], "experiment and split starts differ")
    _require(experiment_interval["end_exclusive"] == split_interval["end_exclusive"], "experiment and split ends differ")
    checksums = {name: _canonical_checksum(raw) for name, raw in configs.items()}
    split_approved = configs["split"]["approval_status"] == "approved"
    safeguards_approved = configs["safeguards"]["approval_status"] == "approved"
    return V3ConfigBundle(
        **configs,
        checksums=checksums,
        ready_for_label_implementation=split_approved and safeguards_approved,
        ready_for_policy_optimization=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Milestone 1 v3 configuration contracts")
    parser.add_argument("--config-root", type=Path, default=DEFAULT_CONFIG_ROOT)
    args = parser.parse_args(argv)
    bundle = load_and_validate_v3_configs(args.config_root)
    print(json.dumps({
        "status": "valid",
        "checksums": dict(bundle.checksums),
        "ready_for_label_implementation": bundle.ready_for_label_implementation,
        "ready_for_policy_optimization": bundle.ready_for_policy_optimization,
        "pending_approval": not bundle.ready_for_label_implementation,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
