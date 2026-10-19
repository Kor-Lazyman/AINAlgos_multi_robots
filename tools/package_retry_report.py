"""Freeze the completed retry1 evaluation and render its Validator Gantt view."""
from pathlib import Path
import csv, hashlib, html, json, shutil, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/train_e_retry1_40updates_20261019'
REPORT = ROOT / 'report_final'
DEST = REPORT / '1.1.1e-retry1'
sys.path.insert(0, str(ROOT / 'environment/src'))
from waam_validator import load_config, load_trajectory_csv
from waam_validator.dashboard.preview import build_gantt_figure

EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
NAMES = ['Honeycomb', 'Spiral', 'Triangular truss', 'Motor inner', 'Twisted shell', 'Angle frame']


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def fmt(seconds):
    n = round(float(seconds)); d, n = divmod(n, 86400)
    h, n = divmod(n, 3600); m, s = divmod(n, 60)
    return f'{d:02}:{h:02}:{m:02}:{s:02}'


def copydir(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))


def validator_gantt(job):
    """Use the same WAAM Validator figure builder as the dashboard."""
    inputs = job / 'input'
    config = load_config(inputs / 'config.yaml')
    trajectory = load_trajectory_csv(inputs / 'trajectory.csv', config)
    figure = build_gantt_figure(trajectory)
    figure.update_layout(width=1600, height=380, margin=dict(l=75,r=35,t=90,b=45))
    page = job / 'waam_validator_gantt.html'
    page.write_text('<!doctype html><meta charset="utf-8"><title>WAAM Validator Gantt</title>'
                    '<style>body{margin:0;background:#0d1927}</style>'
                    + figure.to_html(full_html=False, include_plotlyjs=True), encoding='utf-8')
    png = job / 'waam_validator_gantt.png'
    profile = job / '_capture_profile'
    command = [str(EDGE), '--headless=new', '--disable-gpu', '--hide-scrollbars',
               '--no-first-run', '--disable-features=MediaRouter',
               '--virtual-time-budget=10000', f'--user-data-dir={profile}',
               '--window-size=1650,500', f'--screenshot={png}', page.as_uri()]
    result = subprocess.run(command, capture_output=True, timeout=70)
    if result.returncode or not png.is_file() or png.stat().st_size < 5_000:
        raise RuntimeError(f'Browser capture failed for {job.name}: {result.stderr[-500:]}')
    shutil.rmtree(profile)
    return png


def main():
    state = json.loads((RUN/'training.json').read_text(encoding='utf-8'))
    if state['status'] != 'complete' or state['completed_updates'] != 40:
        raise RuntimeError('40-update training is incomplete')
    if DEST.exists():
        raise RuntimeError('Frozen retry1 package already exists')
    DEST.mkdir()
    (DEST/'model').mkdir()
    for n in ['final_model.zip','best_model.zip','initial_model.zip','training.json']:
        shutil.copy2(RUN/n, DEST/'model'/n)
    copydir(RUN/'source', DEST/'runtime')
    copydir(ROOT/'environment', DEST/'runtime/environment')
    shutil.copy2(REPORT/'1.1.1e/test-version.py', DEST/'test-version.py')
    shutil.copy2(REPORT/'1.1.1e/runtime/test-version.py', DEST/'runtime/test-version.py')
    all_rows = []
    for kind, filename in [('stl_files','final_stl.csv'),('validation_data','final_validation.csv')]:
        target = DEST/kind;target.mkdir()
        with (RUN/filename).open(encoding='utf-8-sig',newline='') as stream:
            rows = list(csv.DictReader(stream))
        for item in rows:
            if item['status'] != 'complete' or item['validator_status'] != 'PASS':
                raise RuntimeError(f'Incomplete Validator result: {item["job"]}')
            source = Path(item['artifact_dir'])
            job = target/item['job']
            copydir(source, job)
            original = ROOT/('train' if kind=='stl_files' else 'validation')/item['job']
            copydir(original, job/'original_input')
            summary = json.loads((job/'validation/summary.json').read_text(encoding='utf-8'))
            if summary['status']!='PASS' or abs(float(summary['schedule']['makespan_s'])-float(item['makespan_s']))>1e-6:
                raise AssertionError('Validator summary does not match result CSV')
            if item['checkpoint_sha256'] != digest(DEST/'model/final_model.zip'):
                raise AssertionError('Reported checkpoint differs from packaged final model')
            validator_gantt(job)
            all_rows.append(dict(variant='1.1.1.e-retry1',split=kind,job=item['job'],
                model_timesteps=item['model_timesteps'],makespan_s=item['makespan_s'],
                makespan_ddhhmmss=fmt(item['makespan_s']),computation_s=item['computation_s'],
                computation_ddhhmmss=fmt(item['computation_s']),
                validator_status=item['validator_status'],checkpoint_sha256=item['checkpoint_sha256'],
                trajectory_sha256=digest(job/'input/trajectory.csv'),
                source_artifact_dir=str(source),artifact_dir=str(job.relative_to(REPORT).as_posix())))
            print(kind,item['job'],'captured',flush=True)
        shutil.copy2(RUN/filename,target/'source_results.csv')
        cards = []
        for row in all_rows:
            if row['split']!=kind:continue
            name=row['job']
            cards.append(f'<h2>{html.escape(name)}</h2><p>{row["makespan_ddhhmmss"]} | Validator PASS</p>'
                         f'<img width="100%" src="{name}/waam_validator_gantt.png">'
                         f'<p><a href="{name}/waam_validator_gantt.html">Interactive Validator Gantt</a> '
                         f'<a href="{name}/input/trajectory.csv">Trajectory</a> '
                         f'<a href="{name}/validation/summary.json">Validator JSON</a></p>')
        (target/'index.html').write_text('<meta charset="utf-8"><style>body{max-width:1150px;'
            'margin:auto;font-family:Arial}</style><h1>1.1.1.e retry1 '+kind+'</h1>'
            +''.join(cards),encoding='utf-8')
    with (DEST/'results.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(all_rows[0]))
        writer.writeheader();writer.writerows(all_rows)
    (DEST/'results.json').write_text(json.dumps(all_rows,indent=2,ensure_ascii=False),encoding='utf-8')
    (DEST/'README.md').write_text('40-update retry1 final checkpoint. '
        'WAAM Validator Gantt images are Edge captures of the bundled Validator dashboard '
        'build_gantt_figure using each PASS evaluation trajectory. '
        'Computation time is measured per STL by the evaluation runner, '
        'separate from the complete training wall time.\n',encoding='utf-8')
    print('Packaged',len(all_rows),'PASS evaluations',flush=True)

if __name__=='__main__':main()
