import argparse,json
from pathlib import Path
from ml.training_dataset.config import DEFAULT_CONFIG_PATH,load_training_config
from ml.training_dataset.pipeline import build_training_dataset
from ml.training_dataset.export import export_training
from ml.training_dataset.report import build_report,write_reports


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--config",type=Path,default=DEFAULT_CONFIG_PATH); p.add_argument("--limit",type=int)
    p.add_argument("--dry-run",action="store_true"); p.add_argument("--overwrite",action="store_true"); a=p.parse_args(argv)
    if a.limit is not None and a.limit < 100: raise ValueError("--limit must be at least 100 for temporal splits")
    c=load_training_config(a.config); result=build_training_dataset(c,limit=a.limit); output=None; files=(); reports=()
    if not a.dry_run: output,files,_=export_training(result,c,a.overwrite)
    report=build_report(result,files)
    if not a.dry_run: reports=write_reports(report,c.reports_root)
    print(json.dumps({"dry_run":a.dry_run,"output":str(output) if output else None,"reports":[str(x) for x in reports],"summary":report},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())

