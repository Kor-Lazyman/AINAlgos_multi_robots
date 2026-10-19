"""Train/evaluate the independent 1.1.1.e coordinate-action handoff PPO."""
import argparse
from datetime import datetime
import hashlib
import json
import shutil
from pathlib import Path
import time
import traceback
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from layer_assignment_env import LayerPathEnv, MultiLayerEnv, VERSION, ACTION_DESCRIPTION, ACTION_NVECS
from validator_adapter import run_validation

ROOT = Path(__file__).resolve().parent


def json_default(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, Path): return str(value)
    raise TypeError(type(value).__name__)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding='utf-8')
    temporary.replace(path)


def jobs(directory):
    directory = Path(directory).resolve()
    if (directory/'target.stl').is_file(): return [directory]
    found = sorted(p.parent for p in directory.glob('*/target.stl') if (p.parent/'config.yaml').is_file())
    if not found: raise ValueError(f'No STL/config jobs in {directory}')
    return found


def dataset_hashes(paths):
    return [{"job": str(p), "target_sha256": hashlib.sha256((p/'target.stl').read_bytes()).hexdigest(),
             "config_sha256": hashlib.sha256((p/'config.yaml').read_bytes()).hexdigest()} for p in paths]


from evaluation_store import evaluate, save_final_tables


class Progress(BaseCallback):
    def __init__(self, output, started, tensorboard=True):
        super().__init__()
        self.output, self.started = Path(output), started
        self.last = time.perf_counter()
        self.gantt = None
        if tensorboard:
            from tools.tensorboard_gantt import LatestGantt
            self.gantt = LatestGantt(output)

    def _on_step(self):
        now = time.perf_counter()
        for info, reward, action in zip(self.locals['infos'], self.locals['rewards'], self.locals['actions']):
            record = dict({k:v for k,v in info.items() if k not in ('task_execution','handoffs')}, step=self.num_timesteps, action=action, reward=float(reward),
                          wall_s=now-self.started, step_wall_s=now-self.last)
            with (self.output/'training_trace.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, default=json_default)+'\n')
            write_json(self.output/'live_progress.json',dict(step=self.num_timesteps,scenario=info.get('scenario_id'),wall_s=now-self.started,layer=info['completed_layers']))
            for key in ('layer_duration_s','mean_robot_utilization','handoff_count','deferred_count','retained_original_count','initially_blocked_count','recovered_own_task_count','retry_check_count'):
                self.logger.record_mean('layer/'+key, float(info[key]))
            for r in range(3):
                self.logger.record_mean(f'robot{r+1}/utilization', info['robot_utilization'][r])
                self.logger.record_mean(f'robot{r+1}/priority_wait_s', info['priority_wait_s'][r])
            if self.num_timesteps % 8 == 0:
                print(f"step={self.num_timesteps} job={info.get('scenario_id')} "
                      f"layer={info['completed_layers']}/{info['total_layers']} "
                      f"duration={info['layer_duration_s']:.2f}s reward={float(reward):.2f} "
                      f"wall={now-self.started:.1f}s", flush=True)
        if self.gantt is not None:
            latest = self.training_env.env_method('get_latest_gantt')[0]
            self.gantt.publish(**latest, step=self.num_timesteps)
        self.last = now
        return True


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['train','eval'], default='train')
    p.add_argument('--train-dir', type=Path, default=ROOT/'train')
    p.add_argument('--validation-dir', type=Path, default=ROOT/'validation')
    p.add_argument('--input', type=Path, help='Evaluation job directory or dataset directory')
    p.add_argument('--checkpoint', type=Path, help='Required for eval; 1.1.1 checkpoint only')
    p.add_argument('--output', type=Path)
    p.add_argument('--updates', type=int, default=40)
    p.add_argument('--n-steps', type=int, default=64)
    p.add_argument('--batch-size', type=int, default=64)
    p.add_argument('--epochs', type=int, default=10)
    p.add_argument('--eval-every', type=int, default=4)
    p.add_argument('--save-every', type=int, default=4)
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--tensorboard', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--official-validator', action=argparse.BooleanOptionalAction, default=True,
                   help='Evaluation diagnostics only; never reward or selection')
    return p


def main():
    p=parser(); args=p.parse_args()
    if min(args.updates,args.n_steps,args.batch_size,args.epochs,args.eval_every,args.save_every)<1:
        p.error('Training counts must be positive')
    if args.batch_size<2 or args.n_steps % args.batch_size:
        p.error('batch-size >= 2 must divide n-steps')
    if args.device.startswith('cuda') and not torch.cuda.is_available(): p.error('CUDA unavailable')
    output=(args.output or ROOT/'output'/f'{args.mode}_{datetime.now():%Y%m%d_%H%M%S}').resolve()
    if output.exists(): p.error('Output directory already exists; choose a fresh destination')
    output.mkdir(parents=True)
    if args.mode=='eval':
        if not args.checkpoint: p.error('--checkpoint is required for eval')
        model=PPO.load(args.checkpoint,device=args.device)
        if not np.array_equal(model.action_space.nvec,ACTION_NVECS): p.error(f'Not a {VERSION} action schema')
        envs=[LayerPathEnv(j) for j in jobs(args.input or args.validation_dir)]
        evaluate(model,envs,output/'evaluation',args.official_validator,split='evaluation',checkpoint=args.checkpoint)
        for env in envs: env.close()
        return
    training_jobs,validation_jobs=jobs(args.train_dir),jobs(args.validation_dir)
    th,vh=dataset_hashes(training_jobs),dataset_hashes(validation_jobs)
    if {j['target_sha256'] for j in th} & {j['target_sha256'] for j in vh}:
        p.error('Training and validation STL hashes overlap')
    started=time.perf_counter()
    (output/'checkpoints').mkdir()
    (output/'source').mkdir()
    for name in ('train.py','layer_assignment_env.py','priority_scheduler.py','validator_adapter.py',
                 '_base_layer_env.py','positioning.py','solid_sampling.py','handoff_scheduler.py','evaluation_store.py'):
        shutil.copy2(ROOT/name,output/'source'/name)
    (output/'source'/'tools').mkdir()
    for name in ('tensorboard_gantt.py', 'smoke_gantt.py'):
        shutil.copy2(ROOT/'tools'/name,output/'source'/'tools'/name)
    settings=dict(version=VERSION,status='initializing',arguments=vars(args),train_jobs=th,validation_jobs=vh,
                  reward='r_layer = -layer_duration_seconds; episode_return = -makespan_seconds',
                  gamma=1.,gae_lambda=0.95,learning_rate=3e-4,early_stopping=False,
                  validator_used_in_reward=False,checkpoint_selection='mean_validation_makespan_s',requested_timesteps=args.updates*args.n_steps,
                  final_csv_files=['final_validation.csv','final_stl.csv','final_results.csv'],
                  action_nvec=ACTION_NVECS,action_description=ACTION_DESCRIPTION,
                  policy='MlpPolicy',network={'pi':[128,128],'vf':[128,128]},
                  geometry_device='cpu',policy_device=args.device,
                  initialization='fresh random policy/value weights; no checkpoint loaded')
    write_json(output/'training.json',settings)
    env=None; validation=[]
    try:
        env=Monitor(MultiLayerEnv(training_jobs))
        validation=[LayerPathEnv(j) for j in validation_jobs]
        model=PPO('MlpPolicy',env,device=args.device,n_steps=args.n_steps,batch_size=args.batch_size,
                  n_epochs=args.epochs,gamma=1.,gae_lambda=0.95,learning_rate=3e-4,seed=args.seed,
                  target_kl=None,policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])),
                  tensorboard_log=str(output/'tensorboard') if args.tensorboard else None,verbose=1)
        model.save(output/'initial_model')
        baseline=evaluate(model,validation,output/'validation_initial',args.official_validator)
        best=baseline['mean_makespan_s']; best_step=0
        model.save(output/'best_model')
        callback=Progress(output,started,tensorboard=args.tensorboard)
        if callback.gantt is not None and hasattr(validation[-1],'latest_layer_rows'):
            last_validation=validation[-1]
            callback.gantt.publish(last_validation.latest_layer_rows,step=0,
                scenario='validation/'+last_validation.scenario.name,layer=last_validation.index)
        settings.update(status='training',baseline_mean_makespan_s=best,best_mean_makespan_s=best,
                        actual_timesteps=0,completed_updates=0)
        write_json(output/'training.json',settings)
        training_started=time.perf_counter()
        for update in range(1,args.updates+1):
            model.learn(total_timesteps=args.n_steps,reset_num_timesteps=False,callback=callback,tb_log_name='ppo')
            if update % args.save_every==0 or update==args.updates:
                model.save(output/'checkpoints'/f'ppo_update_{update:04d}')
            model.save(output/'latest_model')
            if update % args.eval_every==0 or update==args.updates:
                result=evaluate(model,validation,output/f'validation_update_{update:04d}',args.official_validator)
                score=result['mean_makespan_s']
                if score<best:
                    best=score; best_step=model.num_timesteps; model.save(output/'best_model')
                settings['latest_validation_mean_makespan_s']=score
                model.logger.record('validation/makespan_s',score)
                model.logger.dump(model.num_timesteps)
            settings.update(completed_updates=update,actual_timesteps=model.num_timesteps,
                            best_mean_makespan_s=best,best_step=best_step,wall_s=time.perf_counter()-started,
                            estimated_remaining_s=(time.perf_counter()-training_started)/update*(args.updates-update))
            write_json(output/'training.json',settings)
            print(f"UPDATE {update}/{args.updates}; remaining estimate {settings['estimated_remaining_s']/3600:.2f} h",flush=True)
        model.save(output/'final_model')
        settings.update(status='trained_evaluating_final',wall_s=time.perf_counter()-started)
        write_json(output/'training.json',settings)
        final_validation=evaluate(model,validation,output/'final_validation',args.official_validator,
                                  split='validation',checkpoint=output/'final_model.zip')
        final_stl=evaluate(model,env.unwrapped.environments,output/'final_stl',args.official_validator,
                           split='train',checkpoint=output/'final_model.zip')
        save_final_tables(output,final_validation,final_stl)
        settings.update(status='complete',wall_s=time.perf_counter()-started,
                        final_validation_completed=final_validation['completed_jobs'],
                        final_stl_completed=final_stl['completed_jobs'])
        write_json(output/'training.json',settings)
    except BaseException as exc:
        settings.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
                        error=repr(exc),traceback=traceback.format_exc(),wall_s=time.perf_counter()-started)
        write_json(output/'training.json',settings)
        raise
    finally:
        if env: env.close()
        for item in validation: item.close()


if __name__=='__main__': main()
