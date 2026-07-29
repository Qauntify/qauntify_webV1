from pathlib import Path
import json
import pytest
import yaml
from ml.training.v3_data import load_training_v3


def test_v3_config_is_directional_and_test_forbidden():
    cfg=yaml.safe_load(Path('ml/configs/classifiers_v3.yaml').read_text('utf-8'))
    assert cfg['directions']==['long','short']
    assert cfg['models']==['prevalence','logistic_regression','shallow_tree','random_forest','catboost']
    assert cfg['evaluation']['untouched_test_access']=='forbidden'
    assert cfg['evaluation']['use_all_five_walk_forward_folds'] is True


def test_loader_has_no_test_parameter():
    import inspect
    assert 'split' not in inspect.signature(load_training_v3).parameters


def test_frozen_training_manifest():
    manifest=json.loads(Path('ml/data/datasets/training_v3/training_manifest.json').read_text('utf-8'))
    assert manifest['approval_status']=='approved_frozen'
    assert manifest['untouched_test_locked'] is True
    assert len(manifest['model_feature_columns'])==81


def test_cli_exposes_persistent_resume_and_dataset_override():
    source=Path('ml/training/v3_cli.py').read_text('utf-8')
    assert "'--resume'" in source and "'--dataset-root'" in source
