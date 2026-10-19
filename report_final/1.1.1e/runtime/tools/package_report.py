"""Freeze existing results and runtime before scheduler edits. No evaluations."""
from pathlib import Path
import csv, hashlib, json, shutil, html, zipfile
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent
OLD=BASE/'version 1.0.1/report final'
RUN=ROOT/'output/train_e_40updates_20261019'
DEST=ROOT/'report_final'
MINOR_VAL=BASE/'version 1.0.2/AInalgos2-main/backups/minor_2/result/training/reward_only_40updates_20261018_155838/validation/step_00002560'
NAMES=['Honeycomb','Spiral','Triangular truss','Motor inner','Twisted shell','Angle frame']
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def copytree(a,b): shutil.copytree(a,b,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
def table(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def fmt(s):
    s=round(float(s));d,s=divmod(s,86400);h,s=divmod(s,3600);m,s=divmod(s,60)
    return f'{d:02}:{h:02}:{m:02}:{s:02}'

def gantt(job,title):
    rows=[[],[],[]]
    with (job/'input/trajectory.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):rows[int(r['robot_id'])-1].append((float(r['time_s']),r['mode']))
    end=max(own[-1][0] for own in rows)
    im=Image.new('RGB',(1600,400),'white');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',29)
    small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',25)
    d.text((20,8),title,fill='black',font=font)
    colors={'D':'#ed8936','T':'#3182ce','W':'#a0aec0'}
    for i,own in enumerate(rows):
        y=74+i*75;d.text((20,y),f'R{i+1}',fill='black',font=font)
        for a,b in zip(own,own[1:]):
            if b[0]>a[0]:d.rectangle((95+a[0]/end*1470,y,95+b[0]/end*1470,y+39),fill=colors[a[1]])
    d.text((95,302),f'0 s',fill='black',font=small)
    d.text((1050,302),f'{end:,.2f} s',fill='black',font=small)
    d.text((95,350),'Orange: deposition     Blue: travel     Gray: wait',fill='black',font=small)
    im.save(job/'gantt.png')

def make_index(folder,records):
    cards=[]
    for r in records:
        j=r['job'];cards.append(f'<h2>{html.escape(j)}</h2><p>Makespan {fmt(r["makespan_s"])} | Validator {r["validator_status"]}</p><img width="100%" src="{j}/gantt.png"><p><a href="{j}/input/trajectory.csv">Trajectory CSV</a> | <a href="{j}/input/target.stl">STL</a> | <a href="{j}/validation/summary.json">WAAM Validator JSON</a> | <a href="{j}/validation/validation_report.md">Validator report</a></p>')
    (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{max-width:1100px;margin:40px auto;font-family:Arial}img{border:1px solid #ddd}</style>'+''.join(cards),encoding='utf-8')

def main():
    DEST.mkdir(exist_ok=True)
    copytree(OLD/'common/environment',DEST/'common/environment')
    datasets={}
    for variant in ['minor2','1.1.1e']:
        out=DEST/variant;(out/'model').mkdir(parents=True,exist_ok=True)
        if variant=='minor2':
            copytree(OLD/'minor2/runtime',out/'runtime')
            shutil.copy2(OLD/'minor2/test-version.py',out/'test-version.py')
            srcmodel=OLD/'minor2/stl_files/model_snapshot.zip'
            with zipfile.ZipFile(srcmodel) as a, zipfile.ZipFile(MINOR_VAL/'model_snapshot.zip') as b:
                assert a.read('policy.pth')==b.read('policy.pth'),'Minor2 validation policy mismatch'
            shutil.copy2(MINOR_VAL/'model_snapshot.zip',out/'model/validation_snapshot.zip')
            shutil.copy2(srcmodel,out/'model/final_model.zip')
            launcher=(out/'test-version.py').read_text(encoding='utf-8').replace('"best_model.zip"','"final_model.zip"')
            (out/'test-version.py').write_text(launcher,encoding='utf-8')
            write(out/'model/training.json',read(OLD/'minor2/stl_files/evaluation.json')['training'])
        else:
            (out/'runtime').mkdir(exist_ok=True)
            for p in ROOT.glob('*.py'):shutil.copy2(p,out/'runtime'/p.name)
            copytree(ROOT/'tools',out/'runtime/tools');copytree(ROOT/'environment',out/'runtime/environment')
            for n in ['final_model.zip','best_model.zip','training.json']:shutil.copy2(RUN/n,out/'model'/n)
            launcher='''"""Frozen 1.1.1.e final checkpoint; evaluate one original STL."""
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
'''
            (out/'test-version.py').write_text(launcher,encoding='utf-8')
        for split in ['stl_files','validation_data']:
            folder=out/split;folder.mkdir(exist_ok=True);records=[]
            if variant=='minor2':
                source=OLD/'minor2/stl_files' if split=='stl_files' else MINOR_VAL
                ev=read(source/'evaluation.json');shutil.copy2(source/'evaluation.json',folder/'source_evaluation.json')
                if 'jobs' not in ev:
                    ev['jobs']=[dict(j,episodes=[ep],job_wall_time_s=ep['wall_time_s']) for j,ep in zip(ev['validation_jobs'],ev['episodes'])]
                for i,j in enumerate(ev['jobs']):
                    name=f'{i+1:02}' if split=='stl_files' else j['id']
                    src=source/f'job_{i:02}/episode_000';dst=folder/name;copytree(src,dst)
                    ep=j['episodes'][0]
                    rm=list(csv.DictReader((dst/'validation/robot_metrics.csv').open(encoding='utf-8-sig')))
                    util=[(float(x['deposition_time_s'])+float(x['travel_time_s']))/ep['makespan_s'] for x in rm]
                    records.append(dict(version=variant,split=split,job=name,model_timesteps=ev.get('model_timesteps',2560),checkpoint_sha256=sha(out/'model/final_model.zip'),makespan_s=ep['makespan_s'],computation_s=j['job_wall_time_s'],validator_status=ep['status'],layers=ep['total_layers'],robot1_utilization=util[0],robot2_utilization=util[1],robot3_utilization=util[2],artifact_dir=f'{variant}/{split}/{name}',source_artifact_dir=str(src),target_sha256=j['input_sha256']['target.stl']))
            else:
                src_csv=RUN/('final_stl.csv' if split=='stl_files' else 'final_validation.csv')
                for r in csv.DictReader(src_csv.open(encoding='utf-8-sig')):
                    src=Path(r['artifact_dir']);name=r['job'];dst=folder/name;copytree(src,dst)
                    original=ROOT/('train' if split=='stl_files' else 'validation')/name
                    copytree(original,dst/'original_input')
                    records.append(dict(version=variant,split=split,job=name,model_timesteps=int(r['model_timesteps']),checkpoint_sha256=r['checkpoint_sha256'],makespan_s=float(r['makespan_s']),computation_s=float(r['computation_s']),validator_status=r['validator_status'],layers=int(r['layers']),robot1_utilization=float(r['robot1_utilization']),robot2_utilization=float(r['robot2_utilization']),robot3_utilization=float(r['robot3_utilization']),artifact_dir=f'{variant}/{split}/{name}',source_artifact_dir=str(src),target_sha256=r['target_sha256']))
            for r in records:
                dst=folder/r['job'];gantt(dst,variant+' | '+r['job'])
                assert r['checkpoint_sha256']==sha(out/'model/final_model.zip')
                write(dst/'packaged_result.json',r)
            table(folder/'results.csv',records);make_index(folder,records);datasets[(variant,split)]=records
        write(out/'model/checkpoint_manifest.json',dict(evaluated_checkpoint='final_model.zip',sha256=sha(out/'model/final_model.zip'),timesteps=2560,other_checkpoint_note='best_model.zip is validation-best at step 2048, not used in report' if variant=='1.1.1e' else None))
    allrows=[r for rows in datasets.values() for r in rows];table(DEST/'all_results.csv',allrows)
    write(DEST/'report_data.json',allrows)
    manifest=[]
    for p in sorted(DEST.rglob('*')):
        if p.is_file() and p.name!='manifest.json':manifest.append(dict(path=p.relative_to(DEST).as_posix(),size=p.stat().st_size,sha256=sha(p)))
    write(DEST/'manifest.json',manifest)
    (DEST/'README.md').write_text('''# Minor2 및 1.1.1.e 최종 결과

두 실험의 2,560-step 모델과 저장된 평가 결과입니다. 1.1.1.e는 스케줄러 변경 전 40-update 최종 모델입니다. best_model.zip(32-update)은 별도 보관하며 보고서 수치에는 사용하지 않았습니다.

각 실험 폴더에는 model, runtime, stl_files, validation_data, pseudocode와 test-version.py가 있습니다. 각 입력 폴더의 input에는 Validator에 사용한 STL/config/trajectory, validation에는 공식 Validator JSON과 CSV, gantt.png에는 저장 trajectory로 그린 간트가 있습니다. e의 original_input은 위치 조정 전 입력이며, 재실행에는 이것을 사용합니다. input/target.stl은 이미 이동된 STL이므로 e 재실행에 사용하면 위치 조정이 중복될 수 있습니다.

## 실행

```powershell
& 'C:\\Users\\lazzyman\\anaconda3\\envs\\waam\\python.exe' .\\minor2\\test-version.py --stl .\\minor2\\stl_files\\01\\input\\target.stl
& 'C:\\Users\\lazzyman\\anaconda3\\envs\\waam\\python.exe' .\\1.1.1e\\test-version.py --stl .\\1.1.1e\\stl_files\\01\\original_input\\target.stl
```

생성물은 각 실험의 output에 저장합니다. --config, --device cpu, --output 옵션을 사용할 수 있습니다. 기존 모델을 불러오는 평가이며 재학습하지 않습니다.

all_results.csv에 정확한 초 단위 수치와 체크포인트 SHA256, 원본 출처가 있습니다. 활용률은 (이동+적층)/makespan이며 동시 적층률과 다릅니다. 계산시간은 각 실행에 저장된 측정값으로 하드웨어·캐시·측정 범위가 완전히 통제된 벤치마크는 아닙니다. minor2 validation은 기존 report final의 256-step 대신 같은 2,560-step 체크포인트 평가를 사용합니다. e의 추가 validation 2개는 minor2 비교 결과가 없습니다.

보고서의 설명 및 코멘트 칸은 작성자가 채울 수 있게 비워 두었습니다. TensorBoard 파일은 포함하지 않습니다.
''',encoding='utf-8')
    (DEST/'index.html').write_text('<meta charset="utf-8"><h1>Minor2 and 1.1.1.e</h1>'+''.join(f'<p><a href="{v}/{s}/index.html">{v} {s}</a></p>' for v,s in datasets)+'<p><a href="combined_report.docx">Word report</a></p>',encoding='utf-8')
    print('Packaged',len(allrows),'results',len(manifest),'files',flush=True)
if __name__=='__main__':main()
