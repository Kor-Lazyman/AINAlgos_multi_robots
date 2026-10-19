"""Frozen 1.1.1.e final checkpoint; evaluate one original STL."""
from pathlib import Path
import argparse,subprocess,sys
from datetime import datetime
ROOT=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--stl',type=Path,required=True)
 p.add_argument('--config',type=Path)
 p.add_argument('--device',default='cuda')
 p.add_argument('--output',type=Path)
 a=p.parse_args(); stl=a.stl.resolve(); cfg=(a.config or stl.parent/'config.yaml').resolve()
 if not stl.is_file() or not cfg.is_file():p.error('STL and config.yaml must exist')
 out=(a.output or ROOT/'output'/datetime.now().strftime('%Y%m%d_%H%M%S')).resolve()
 return subprocess.call([sys.executable,str(ROOT/'runtime/test-version.py'),'--input',str(stl),'--config',str(cfg),'--checkpoint',str(ROOT/'model/final_model.zip'),'--output',str(out),'--device',a.device,'--official-validator'],cwd=ROOT/'runtime')
if __name__=='__main__':raise SystemExit(main())
