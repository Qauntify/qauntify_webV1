"""Directional v3 baseline and untuned CatBoost classifier runner."""
from __future__ import annotations
import hashlib, json, platform
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.calibration import calibration_curve
from sklearn.compose import make_column_transformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from ml.training.v3_data import load_training_v3


def _sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest().upper()


def _model(name, cfg, seed, smoke):
    b=cfg['baseline']
    if name=='prevalence': return DummyClassifier(strategy='prior')
    if name=='logistic_regression': return make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),LogisticRegression(max_iter=int(b['logistic_max_iterations']),random_state=seed))
    if name=='shallow_tree': return make_pipeline(SimpleImputer(strategy='median'),DecisionTreeClassifier(max_depth=int(b['shallow_tree_max_depth']),random_state=seed))
    if name=='random_forest': return make_pipeline(SimpleImputer(strategy='median'),RandomForestClassifier(n_estimators=int(b['random_forest_trees']),max_depth=int(b['random_forest_max_depth']),n_jobs=-1,random_state=seed))
    from catboost import CatBoostClassifier
    c=cfg['catboost'].copy(); configured_iterations=int(c.pop('iterations')); c.pop('early_stopping_rounds')
    iterations=int(cfg['smoke']['catboost_iterations']) if smoke else configured_iterations
    return CatBoostClassifier(iterations=iterations,loss_function='Logloss',eval_metric='AUC',random_seed=seed,verbose=False,allow_writing_files=False,**c)


def _metrics(y,p):
    return {'rows':len(y),'positive_rate':float(np.mean(y)),'roc_auc':float(roc_auc_score(y,p)),'pr_auc':float(average_precision_score(y,p)),'log_loss':float(log_loss(y,p,labels=[0,1])),'brier_score':float(brier_score_loss(y,p))}


def run(config_path:Path, experiment_dir:Path, *, smoke=False, resume=False, dataset_root:Path|None=None):
    cfg=yaml.safe_load(config_path.read_text('utf-8')); root=dataset_root.resolve() if dataset_root else config_path.parents[2]/cfg['dataset_root']
    manifest=json.loads((root/'training_manifest.json').read_text('utf-8'))
    if manifest.get('approval_status')!='approved_frozen': raise ValueError('training_v3 must be approved_frozen')
    limits={'train_rows':int(cfg['smoke']['train_rows']),'validation_rows':int(cfg['smoke']['validation_rows'])} if smoke else None
    data_manifest,features,frames,folds=load_training_v3(root,smoke=limits)
    identity=hashlib.sha256(json.dumps({'config':cfg,'dataset_checksum':data_manifest['dataset_checksum'],'smoke':smoke},sort_keys=True).encode()).hexdigest()
    state_path=experiment_dir/'run_state.json';metrics_path=experiment_dir/'metrics.json'
    if experiment_dir.exists():
        if not resume: raise FileExistsError(f'Experiment exists: {experiment_dir}; use --resume')
        if not state_path.is_file(): raise ValueError('Existing experiment has no run_state.json')
        state=json.loads(state_path.read_text('utf-8'))
        if state.get('identity')!=identity: raise ValueError('Resume identity does not match config or dataset')
    else:
        experiment_dir.mkdir(parents=True);state={'identity':identity,'status':'running','completed_jobs':[]};state_path.write_text(json.dumps(state,indent=2)+'\n','utf-8')
    results=json.loads(metrics_path.read_text('utf-8')) if metrics_path.is_file() else {}
    scopes={'primary':frames,**{f'fold_{k}':v for k,v in folds.items()}}
    for scope,parts in scopes.items():
        results.setdefault(scope,{})
        for direction in cfg['directions']:
            target=f'{direction}_net_profitable';results[scope].setdefault(direction,{})
            X_train=parts['train'][features];y_train=parts['train'][target].astype(int)
            X_val=parts['validation'][features];y_val=parts['validation'][target].astype(int)
            for name in cfg['models']:
                job_id=f'{scope}/{direction}/{name}'
                if job_id in state['completed_jobs']: continue
                model=_model(name,cfg,int(cfg['random_seed']),smoke)
                if name=='catboost': model.fit(X_train,y_train,eval_set=(X_val,y_val),early_stopping_rounds=min(int(cfg['catboost']['early_stopping_rounds']),3 if smoke else int(cfg['catboost']['early_stopping_rounds'])))
                else:model.fit(X_train,y_train)
                p=model.predict_proba(X_val)[:,1];results[scope][direction][name]=_metrics(y_val,p)
                pred=pd.DataFrame({'candidate_id':parts['validation'].candidate_id,'decision_timestamp':parts['validation'].decision_timestamp,'scope':scope,'direction':direction,'model':name,'target':y_val,'raw_probability':p})
                prediction_path=experiment_dir/'predictions'/scope/direction;prediction_path.mkdir(parents=True,exist_ok=True);pred.to_parquet(prediction_path/f'{name}.parquet',index=False,compression='zstd')
                path=experiment_dir/'models'/scope/direction;path.mkdir(parents=True,exist_ok=True)
                if name=='catboost':model.save_model(str(path/f'{name}.cbm'))
                else:joblib.dump(model,path/f'{name}.joblib')
                metrics_path.write_text(json.dumps(results,indent=2,sort_keys=True)+'\n','utf-8');state['completed_jobs'].append(job_id);state_path.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n','utf-8')
    resolved={**cfg,'dataset_checksum':data_manifest['dataset_checksum'],'smoke':smoke};(experiment_dir/'config_resolved.yaml').write_text(yaml.safe_dump(resolved,sort_keys=True),'utf-8')
    env={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__};(experiment_dir/'environment.json').write_text(json.dumps(env,indent=2)+'\n','utf-8')
    state['status']='complete';state_path.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n','utf-8')
    base_files=sorted(p for p in experiment_dir.rglob('*') if p.is_file() and p.name not in {'artifact_checksums.json','experiment_manifest.json'})
    run_manifest={'version':'classifiers_v3','smoke':smoke,'status':'complete','untouched_test_accessed':False,'directions':cfg['directions'],'models':cfg['models'],'scopes':list(scopes),'dataset_checksum':data_manifest['dataset_checksum'],'completed_jobs':len(state['completed_jobs']),'expected_jobs':60,'resume_supported':True,'artifact_count':len(base_files)+2};(experiment_dir/'experiment_manifest.json').write_text(json.dumps(run_manifest,indent=2,sort_keys=True)+'\n','utf-8')
    files=sorted([*base_files,experiment_dir/'experiment_manifest.json']);checks={str(p.relative_to(experiment_dir)).replace('\\','/'):_sha(p) for p in files};(experiment_dir/'artifact_checksums.json').write_text(json.dumps(checks,indent=2,sort_keys=True)+'\n','utf-8');return run_manifest
