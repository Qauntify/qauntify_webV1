import argparse,json
from pathlib import Path
from ml.outcomes.label_v3 import load_m5_csv
from ml.features.feature_v3_pipeline import build,export
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--output',type=Path,default=Path('ml/data/processed/features_v3'));p.add_argument('--overwrite',action='store_true');a=p.parse_args();m5=load_m5_csv(Path('ml/data/raw/xauusd_m5_2016_2026.csv'),limit=a.limit);m15=load_m5_csv(Path('ml/data/raw/xauusd_m15_2016_2026.csv'));r=export(build(m5,m15),a.output,a.overwrite);print(json.dumps(r,indent=2))
if __name__=='__main__':main()
