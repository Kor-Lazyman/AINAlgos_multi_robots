"""Versioned evaluation CSVs and reusable, content-addressed numerical results."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import time
import traceback
import numpy as np
from validator_adapter import run_validation

ROOT=Path(__file__).resolve().parent
FIELDS=['version','split','job','status','model_timesteps','policy_sha256','checkpoint_sha256',
        'target_sha256','config_sha256','code_sha256','cache_key','cache_hit','makespan_s',
        'computation_s','validator_status','validator_wall_s','collision_events','iou','layers',
        'robot1_utilization','robot2_utilization','robot3_utilization','artifact_dir','error']


def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)),encoding='utf-8')
    temp.replace(path)


def write_csv(path,records):
    """Excel-readable UTF-8 BOM; failed/incomplete makespans stay blank."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');writer.writeheader()
        for record in records:
            row=dict(record)
            for i,robot in enumerate(record.get('robots',[]),1): row[f'robot{i}_utilization']=robot['utilization']
            writer.writerow(row)
    temp.replace(path)


def fingerprint(model):
    digest=hashlib.sha256()
    for key,value in sorted(model.policy.state_dict().items()):
        digest.update(key.encode());digest.update(value.detach().cpu().numpy().tobytes())
    code=hashlib.sha256()
    paths=list(ROOT.glob('*.py'))+list((ROOT/'environment'/'src').rglob('*.py'))
    for path in sorted(paths):
        code.update(str(path.relative_to(ROOT)).encode());code.update(path.read_bytes())
    return digest.hexdigest(),code.hexdigest()


def evaluate(model,environments,output,official=False,split='validation',checkpoint=None):
    from layer_assignment_env import VERSION
    from tools.smoke_gantt import chart
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    policy_hash,code_hash=fingerprint(model)
    checkpoint_hash=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest() if checkpoint else ''
    cache=ROOT/'output'/'evaluation_cache';records=[]
    def persist():
        write_csv(output/'results.csv',records)
        if output.name in ('final_stl','final_validation'):
            write_csv(output.parent/(output.name+'.csv'),records)
    for env in environments:
        state=dict(version=VERSION,split=split,job=env.scenario.name,model_timesteps=int(model.num_timesteps),
                   policy_sha256=policy_hash,checkpoint_sha256=checkpoint_hash,code_sha256=code_hash,
                   target_sha256=hashlib.sha256((env.scenario/'target.stl').read_bytes()).hexdigest(),
                   config_sha256=hashlib.sha256((env.scenario/'config.yaml').read_bytes()).hexdigest())
        keydata={k:state[k] for k in ('version','job','policy_sha256','code_sha256','target_sha256','config_sha256')}
        keydata.update(seed=1042,deterministic=True,official_validator=official,schema='evaluation_cache_v1')
        key=hashlib.sha256(json.dumps(keydata,sort_keys=True).encode()).hexdigest()
        cache_file=cache/key/'result.json';state.update(cache_key=key,cache_hit=False)
        if cache_file.is_file():
            saved=json.loads(cache_file.read_text(encoding='utf-8'))
            if Path(saved['artifact_dir'],'input','trajectory.csv').is_file():
                saved.update(state,cache_hit=True);records.append(saved)
                write_json(output/env.scenario.name/'cached_result.json',saved)
                persist()
                print(f'EVAL CACHE {env.scenario.name}: {saved["makespan_s"]:.3f}s',flush=True)
                continue
        started=time.perf_counter();destination=output/env.scenario.name
        try:
            observation,_=env.reset(seed=1042);episode_reward=0.
            print(f'EVAL BEGIN {env.scenario.name}: {len(env.layers)} layers',flush=True)
            while not env.done:
                action,_=model.predict(observation,deterministic=True)
                observation,reward,_,_,info=env.step(action);episode_reward+=reward
                write_json(output/'evaluation_progress.json',dict(job=env.scenario.name,
                    completed_layers=env.index,total_layers=len(env.layers),wall_s=time.perf_counter()-started))
            if not np.isclose(episode_reward,-env.makespan):raise AssertionError('Reward is not pure negative makespan')
            env.export(destination/'input');write_json(destination/'layer_trace.json',env.layer_history)
            robots=[]
            for own in env.rows:
                times={m:sum(b[0]-a[0] for a,b in zip(own,own[1:]) if a[4]==m) for m in ('D','T','W')}
                robots.append(dict(deposition_s=times['D'],travel_s=times['T'],wait_s=times['W'],
                                   utilization=(times['D']+times['T'])/env.makespan,
                                   deposition_utilization=times['D']/env.makespan))
            state.update(status='complete',makespan_s=env.makespan,reward=episode_reward,
                         computation_s=time.perf_counter()-started,layers=len(env.layers),robots=robots,
                         collision_certified=True,validator_status='NOT_RUN',artifact_dir=str(destination.resolve()))
            if official:
                vstart=time.perf_counter();result=run_validation(destination/'input',destination/'validation')
                state.update(validator_status=result.status,validator_wall_s=time.perf_counter()-vstart,
                             collision_events=len(result.collision.events),iou=result.shape.iou)
            chart(destination,env.rows,f'{VERSION} | {env.scenario.name} | {model.num_timesteps} training steps')
            write_json(destination/'metrics.json',state);write_json(cache_file,state)
        except Exception as exc:
            state.update(status='failed',makespan_s=None,error=repr(exc),traceback=traceback.format_exc(),
                         artifact_dir=str(destination.resolve()),computation_s=time.perf_counter()-started)
            write_json(destination/'failure.json',state)
        records.append(state);persist()
        print(f'EVAL {env.scenario.name}: status={state["status"]} makespan={state.get("makespan_s")} cache={state["cache_hit"]}',flush=True)
    completed=[r for r in records if r['status']=='complete']
    result=dict(version=VERSION,split=split,jobs=records,completed_jobs=len(completed),
                mean_makespan_s=float(np.mean([r['makespan_s'] for r in completed])) if len(completed)==len(records) else float('inf'))
    write_json(output/'summary.json',result)
    return result


def save_final_tables(output,validation,stl):
    output=Path(output)
    write_csv(output/'final_validation.csv',validation['jobs'])
    write_csv(output/'final_stl.csv',stl['jobs'])
    write_csv(output/'final_results.csv',validation['jobs']+stl['jobs'])
    write_json(output/'final_evaluation.json',dict(validation=validation,stl=stl))
