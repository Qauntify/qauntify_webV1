"""Configuration and Hugging Face loading for the offline XAUUSD pipeline.

This module intentionally is not named ``datasets.py`` so it cannot shadow the
third-party Hugging Face package.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "ml" / "configs" / "xauusd_dataset.yaml"

CANONICAL_TIMEFRAMES = frozenset({
    "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1",
})


class DatasetConfigurationError(ValueError):
    """Dataset configuration is incomplete, unsafe, or internally inconsistent."""


@dataclass(frozen=True)
class DatasetConfig:
    dataset_name: str
    revision: str
    symbol: str
    output_root: Path
    report_root: Path
    cache_root: Path
    partition_columns: tuple[str, ...]
    compression: str
    remove_exact_duplicates: bool
    fail_on_invalid_ohlc: bool
    fail_on_unknown_timeframe: bool
    source_timeframes: dict[str, str]

    def cleaning_settings(self) -> dict:
        return {
            "remove_exact_duplicates": self.remove_exact_duplicates,
            "fail_on_invalid_ohlc": self.fail_on_invalid_ohlc,
            "fail_on_unknown_timeframe": self.fail_on_unknown_timeframe,
        }


@dataclass(frozen=True)
class HubInventory:
    dataset_name: str
    requested_revision: str
    resolved_revision: str | None
    configurations: tuple[str, ...]
    splits_by_configuration: dict[str, tuple[str, ...]]
    rows_by_configuration_split: dict[str, dict[str, int | None]]
    columns_by_configuration: dict[str, dict[str, str]]
    repository_files: tuple[str, ...]
    source_file_metadata: dict[str, dict]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LoadedTimeframe:
    timeframe: str
    source_file: str
    split_name: str
    dataset: object


def _rooted_path(value: object, field: str) -> Path:
    path = Path(str(value))
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise DatasetConfigurationError(
            f"{field} must remain inside the repository: {resolved}"
        ) from exc
    return resolved


def _required_bool(raw: Mapping, name: str, default: bool) -> bool:
    value = raw.get(name, default)
    if not isinstance(value, bool):
        raise DatasetConfigurationError(f"{name} must be true or false")
    return value


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> DatasetConfig:
    """Load and validate the version-controlled YAML pipeline configuration."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required; install requirements-ml-data.txt") from exc

    config_path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise DatasetConfigurationError("Dataset configuration must be a mapping")

    source_timeframes = raw.get("source_timeframes")
    if not isinstance(source_timeframes, Mapping) or not source_timeframes:
        raise DatasetConfigurationError("source_timeframes must be a non-empty mapping")
    normalized_mapping = {str(name): str(value).upper() for name, value in source_timeframes.items()}
    unknown = sorted(set(normalized_mapping.values()) - CANONICAL_TIMEFRAMES)
    if unknown:
        raise DatasetConfigurationError(f"Unknown configured timeframes: {unknown!r}")
    if len(set(normalized_mapping.values())) != len(normalized_mapping):
        raise DatasetConfigurationError("Each source file must map to a unique timeframe")

    partitions = tuple(str(value) for value in raw.get("partition_columns", ()))
    if partitions != ("symbol", "timeframe", "year"):
        raise DatasetConfigurationError(
            "partition_columns must be exactly: symbol, timeframe, year"
        )

    symbol = str(raw.get("symbol", "XAUUSD")).upper()
    if symbol != "XAUUSD":
        raise DatasetConfigurationError(f"This pipeline only supports XAUUSD, got {symbol!r}")
    compression = str(raw.get("compression", "zstd")).lower()
    if compression not in {"zstd", "snappy"}:
        raise DatasetConfigurationError("compression must be zstd or snappy")

    return DatasetConfig(
        dataset_name=str(raw["dataset_name"]),
        revision=str(raw.get("revision", "main")),
        symbol=symbol,
        output_root=_rooted_path(raw["output_root"], "output_root"),
        report_root=_rooted_path(raw["report_root"], "report_root"),
        cache_root=_rooted_path(raw["cache_root"], "cache_root"),
        partition_columns=partitions,
        compression=compression,
        remove_exact_duplicates=_required_bool(raw, "remove_exact_duplicates", True),
        fail_on_invalid_ohlc=_required_bool(raw, "fail_on_invalid_ohlc", True),
        fail_on_unknown_timeframe=_required_bool(raw, "fail_on_unknown_timeframe", True),
        source_timeframes=normalized_mapping,
    )


def inspect_hub_inventory(config: DatasetConfig) -> HubInventory:
    """Inspect actual Hub configs, splits, features, files, and revision metadata."""
    try:
        from datasets import (
            get_dataset_config_names,
            get_dataset_split_names,
            load_dataset_builder,
        )
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("Hugging Face datasets is required") from exc

    configurations = tuple(get_dataset_config_names(
        config.dataset_name,
        revision=config.revision,
        cache_dir=str(config.cache_root),
    ))
    splits: dict[str, tuple[str, ...]] = {}
    split_rows: dict[str, dict[str, int | None]] = {}
    columns: dict[str, dict[str, str]] = {}
    for configuration in configurations:
        split_names = get_dataset_split_names(
            config.dataset_name,
            configuration,
            revision=config.revision,
            cache_dir=str(config.cache_root),
        )
        splits[configuration] = tuple(split_names)
        builder = load_dataset_builder(
            config.dataset_name,
            configuration,
            revision=config.revision,
            cache_dir=str(config.cache_root),
        )
        columns[configuration] = {
            name: str(feature) for name, feature in builder.info.features.items()
        }
        split_rows[configuration] = {
            split_name: (
                int(builder.info.splits[split_name].num_examples)
                if builder.info.splits and split_name in builder.info.splits
                else None
            )
            for split_name in split_names
        }

    info = HfApi().dataset_info(
        config.dataset_name,
        revision=config.revision,
        files_metadata=True,
    )
    repository_files = tuple(sorted(HfApi().list_repo_files(
        config.dataset_name,
        repo_type="dataset",
        revision=info.sha or config.revision,
    )))
    source_metadata = {}
    for sibling in info.siblings or ():
        if sibling.rfilename not in config.source_timeframes:
            continue
        lfs = sibling.lfs
        source_metadata[sibling.rfilename] = {
            "size_bytes": sibling.size,
            "blob_id": sibling.blob_id,
            "lfs_sha256": (
                lfs.get("sha256")
                if isinstance(lfs, Mapping)
                else getattr(lfs, "sha256", None)
            ),
        }

    return HubInventory(
        dataset_name=config.dataset_name,
        requested_revision=config.revision,
        resolved_revision=info.sha,
        configurations=configurations,
        splits_by_configuration=splits,
        rows_by_configuration_split=split_rows,
        columns_by_configuration=columns,
        repository_files=repository_files,
        source_file_metadata=source_metadata,
    )


def verify_timeframe_sources(config: DatasetConfig, inventory: HubInventory) -> None:
    """Require every trusted timeframe source to exist in the resolved Hub revision."""
    available = set(inventory.repository_files)
    missing = sorted(set(config.source_timeframes) - available)
    if missing:
        raise DatasetConfigurationError(
            f"Configured timeframe source files are missing from the Hub: {missing!r}"
        )
    discovered_sources = {
        name for name in available
        if name.startswith("XAU_") and name.endswith("_data.jsonl")
    }
    unmapped = sorted(discovered_sources - set(config.source_timeframes))
    if unmapped and config.fail_on_unknown_timeframe:
        raise DatasetConfigurationError(
            f"Hub contains unmapped XAUUSD timeframe files: {unmapped!r}"
        )


def iter_timeframe_datasets(
    config: DatasetConfig,
    inventory: HubInventory,
    *,
    streaming: bool = False,
) -> Iterator[LoadedTimeframe]:
    """Load each timeframe file independently so filename provenance is retained."""
    try:
        from datasets import load_dataset as hf_load_dataset
        from huggingface_hub import hf_hub_url
    except ImportError as exc:
        raise RuntimeError("Hugging Face datasets is required") from exc

    verify_timeframe_sources(config, inventory)
    revision = inventory.resolved_revision or config.revision
    for source_file, timeframe in config.source_timeframes.items():
        url = hf_hub_url(
            repo_id=config.dataset_name,
            filename=source_file,
            repo_type="dataset",
            revision=revision,
        )
        dataset = hf_load_dataset(
            "json",
            data_files={"data": url},
            split="data",
            streaming=streaming,
            cache_dir=str(config.cache_root),
        )
        yield LoadedTimeframe(
            timeframe=timeframe,
            source_file=source_file,
            split_name="data",
            dataset=dataset,
        )
