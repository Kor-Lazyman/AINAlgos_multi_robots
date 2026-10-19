"""Compare scheduler revisions with the same saved first-layer actions."""
import csv,json,time
from pathlib import Path
import numpy as np
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from layer_assignment_env import LayerPathEnv
from smoke_test import concurrent_seconds
from tools.smoke_gantt import chart
OUT=ROOT/'output/retry_saved_action_check_20261019'
OUT.mkdir(exist_ok=True)
records=[]
for job in sorted((ROOT/'train').iterdir()):
    if not (job/'target.stl').exists():continue
    before=json.loads((ROOT/'report_final/1.1.1e/stl_files'/job.name/'layer_trace.json').read_text())[0]
    env=LayerPathEnv(job);env.reset(seed=1042);start=time.perf_counter()
    _,reward,_,_,info=env.step(np.array(before['action']))
    assert info['coverage_tasks_complete'] and info['collision_certified']
    assert np.isclose(reward,-info['layer_duration_s'])
    out=OUT/job.name;out.mkdir(exist_ok=True);chart(out,env.latest_layer_rows,'Same first-layer action | retry scheduler | '+job.name)
    (out/'metrics.json').write_text(json.dumps(info,indent=2,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item()),encoding='utf-8')
    r=dict(job=job.name,scope='first_layer_only_same_action_no_retraining',before_s=before['layer_duration_s'],after_s=info['layer_duration_s'],before_handoffs=before['handoff_count'],after_handoffs=info['handoff_count'],recovered_tasks=info['recovered_own_task_count'],collision_certified=True,coverage_complete=True,wall_s=time.perf_counter()-start,**concurrent_seconds(env.latest_layer_rows))
    records.append(r);print(json.dumps(r),flush=True);env.close()
    with (OUT/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
