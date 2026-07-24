import json

import pandas as pd
import pytest

import ml.data.export_dataset as export_module
from ml.data.clean_dataset import clean_dataset
from ml.data.export_dataset import (
    MANIFEST_NAME,
    add_partition_year,
    export_cleaned_dataset,
)
from ml.data.load_dataset import HubInventory


def _inventory():
    return HubInventory(
        dataset_name="fixture/xauusd",
        requested_revision="fixture-revision",
        resolved_revision="resolved-fixture-sha",
        configurations=("default",),
        splits_by_configuration={"default": ("train",)},
        rows_by_configuration_split={"default": {"train": 3}},
        columns_by_configuration={"default": {"Date": "string"}},
        repository_files=("XAU_5m_data.jsonl",),
        source_file_metadata={"XAU_5m_data.jsonl": {"size_bytes": 100}},
    )


def test_partition_year_is_derived_from_timestamp(valid_source_frame, dataset_config):
    cleaned = clean_dataset(
        valid_source_frame,
        config=dataset_config,
        timeframe="M5",
        source_name="XAU_5m_data.jsonl",
    )

    partitioned = add_partition_year(cleaned.candles)

    assert set(partitioned["year"]) == {2024}


def test_partitioned_export_manifest_and_safe_overwrite(
    valid_source_frame, dataset_config, monkeypatch, tmp_path,
):
    pytest.importorskip("pyarrow")
    project_root = dataset_config.output_root.parents[3]
    monkeypatch.setattr(export_module, "PROJECT_ROOT", project_root)
    cleaned = clean_dataset(
        valid_source_frame,
        config=dataset_config,
        timeframe="M5",
        source_name="XAU_5m_data.jsonl",
    )
    report_path = dataset_config.report_root / "xauusd_validation.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{}", encoding="utf-8")

    output = export_cleaned_dataset(
        {"M5": cleaned},
        config=dataset_config,
        inventory=_inventory(),
        validation_report_path=report_path,
    )

    parquet_files = tuple(output.rglob("*.parquet"))
    assert len(parquet_files) == 1
    relative = parquet_files[0].relative_to(output).as_posix()
    assert relative.startswith("symbol=XAUUSD/timeframe=M5/year=2024/")
    exported = pd.read_parquet(parquet_files[0])
    assert "symbol" not in exported
    assert "timeframe" not in exported
    assert "year" not in exported

    manifest = json.loads((output / MANIFEST_NAME).read_text("utf-8"))
    assert manifest["timeframes"] == ["M5"]
    assert manifest["row_count"] == 3
    assert manifest["file_count"] == 1
    assert manifest["huggingface_resolved_revision"] == "resolved-fixture-sha"
    assert len(manifest["checksum"]) == 64

    with pytest.raises(FileExistsError, match="Pass --overwrite"):
        export_cleaned_dataset(
            {"M5": cleaned},
            config=dataset_config,
            inventory=_inventory(),
            validation_report_path=report_path,
        )

    replaced = export_cleaned_dataset(
        {"M5": cleaned},
        config=dataset_config,
        inventory=_inventory(),
        validation_report_path=report_path,
        overwrite=True,
    )
    assert replaced == output
    assert not output.with_name(f".{output.name}.previous").exists()
