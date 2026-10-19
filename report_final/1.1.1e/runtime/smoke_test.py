"""Check handoff continuation, exact coverage, coordinate actions and CSV reuse."""
import argparse
import json
from pathlib import Path
import time
from types import SimpleNamespace
import numpy as np
from stable_baselines3 import PPO
import _base_layer_env as base
from layer_assignment_env import LayerPathEnv, order_from_start
from handoff_scheduler import schedule
from priority_scheduler import first_conflict
from validator_adapter import load_config,trajectory_from_rows,run_validation
from waam_validator.collision.simulator import run_collision_simulation
from evaluation_store import write_json,evaluate
from tools.smoke_gantt import chart

ROOT=Path(__file__).resolve().parent


def concurrent_seconds(rows):
    events=[]
    for own in rows:
        for a,b in zip(own,own[1:]):
            if a[4]=='D':events.extend([(a[0],1),(b[0],-1)])
    n=0;last=0.;triple=0.;double=0.
    for t,delta in sorted(events):
        if n>=2:double+=t-last
        if n==3:triple+=t-last
        n+=delta;last=t
    return dict(two_plus_deposit_s=double,three_deposit_s=triple)


def toy(output):
    cfg=load_config(ROOT/'validation/00_sample/config.yaml');data=cfg.model_dump(mode='json')
    data['collision']['check_arm_envelope']=False
    data['workspace']['radius_mm']=500.
    homes=[[-300.,0.,2.],[0.,-300.,2.],[300.,300.,2.]]
    for robot,home in zip(data['robots'],homes):
        robot.update(home_xyz_mm=home,tcp_radius_mm=10.)
    cfg=type(cfg).model_validate(data)
    env=SimpleNamespace(config=cfg,homes=np.array(homes),
                        bases=np.array([r.base_xyz_mm for r in cfg.robots]),robots=cfg.robots)
    env._move=lambda rows,point,mode:base.LayerPathEnv._move(env,rows,point,mode)
    groups=[ [((-200.,0.),(200.,0.))],
             [((0.,-200.),(0.,200.)),((150.,-200.),(250.,-200.))],
             [((200.,200.),(300.,200.))] ]
    rows,duration,info=schedule(env,groups,2.,(0,1,2))
    assert info['handoff_count']>=1,'Collision handoff not exercised'
    assert info['primary_task_counts'][1]>=1,'Lower robot did not continue safe work'
    assert any(x['from_robot']==2 and x['to_robot']==1 for x in info['handoffs'])
    assert info['coverage_tasks_complete']
    assert not run_collision_simulation(trajectory_from_rows(rows),cfg)
    concurrency=concurrent_seconds(rows)
    assert concurrency['three_deposit_s']>0,'No triple deposition despite safe fixture'
    output.mkdir(parents=True);chart(output,rows,'1.1.1.e | skip crossing, continue safe work, R1 fills skipped task')
    result=dict(makespan_s=duration,**concurrency,**info)
    write_json(output/'metrics.json',result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--all-training-first-layers',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    result={'toy':toy(args.output/'toy')}
    env=LayerPathEnv(ROOT/'validation/00_sample')
    a=np.array([0,0,0,0,32,32,0,32,0,0,0])
    _,reward,_,_,info=env.step(a)
    assert reward==-env.makespan
    env.export(args.output/'sample/input')
    validation=run_validation(args.output/'sample/input',args.output/'sample/validation')
    assert validation.status=='PASS',validation.status
    chart(args.output/'sample',env.rows,'1.1.1.e | sample smoke')
    # Coordinate actions are applied to owned deposition geometry, never air.
    from shapely.geometry import box,Point,LineString
    group=[((0.,0.),(10.,0.)),((0.,10.),(10.,10.))]
    low=order_from_start(group,0,box(0,0,10,10),None,None,[0,0],0)[1]['start_xy']
    high=order_from_start(group,0,box(0,0,10,10),None,None,[32,32],0)[1]['start_xy']
    assert low!=high
    assert min(LineString(s).distance(Point(low)) for s in group)<1e-9
    # Exercise policy update with the expanded action schema using fresh weights.
    model=PPO('MlpPolicy',env,n_steps=4,batch_size=4,n_epochs=1,device='cuda',gamma=1.,seed=123,
              policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
    before={k:v.clone() for k,v in model.policy.state_dict().items()}
    model.learn(4)
    assert any(not before[k].equal(v) for k,v in model.policy.state_dict().items())
    model.save(args.output/'smoke_model')
    first=evaluate(model,[env],args.output/'cache_first',True,checkpoint=args.output/'smoke_model.zip')
    second=evaluate(model,[env],args.output/'cache_second',True,checkpoint=args.output/'smoke_model.zip')
    assert second['jobs'][0]['cache_hit'] and first['mean_makespan_s']==second['mean_makespan_s']
    result['sample']=dict(status=validation.status,coordinate_action_changed_start=True,
                         fresh_ppo_update_verified=True,csv_cache_reuse_verified=True)
    if args.all_training_first_layers:
        result['training_first_layers']=[]
        for job in sorted((ROOT/'train').iterdir()):
            started=time.perf_counter();e=LayerPathEnv(job)
            obs,_=e.reset();action,_=model.predict(obs,deterministic=True)
            _,reward,_,_,info=e.step(action)
            assert info['coverage_tasks_complete'] and info['collision_certified']
            row=dict(job=job.name,wall_s=time.perf_counter()-started,layer_duration_s=-reward,
                     handoff_count=info['handoff_count'],primary_task_counts=info['primary_task_counts'],
                     concurrency=concurrent_seconds(e.latest_layer_rows))
            result['training_first_layers'].append(row);print(json.dumps(row),flush=True)
            write_json(args.output/'summary.json',result);e.close()
    write_json(args.output/'summary.json',result)
    print('SMOKE PASS',flush=True)


if __name__=='__main__':main()
