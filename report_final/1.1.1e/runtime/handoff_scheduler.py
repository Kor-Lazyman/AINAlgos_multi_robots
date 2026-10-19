"""Reserve safe primary work; transfer skipped work without deleting deposition.

Primary work continues past blocked tasks. Deferred work is appended to the
highest-priority reachable robot after its primary route, with home waiting
only if necessary to avoid already reserved trajectories.
"""
from collections import Counter
import numpy as np
from priority_scheduler import pair_conflict, first_conflict, _window, SchedulingInfeasible
from validator_adapter import trajectory_from_rows
from waam_validator.trajectory.validator import validate_trajectory_set


def append_rows(body, tail):
    body[-1][4] = tail[0][4]
    body.extend([list(row) for row in tail[1:]])


def conflict(env, local, planned, robot, rank):
    """Check only a changed interval against every reserved/parked robot."""
    start, end = local[0][0], local[-1][0]
    if end <= start:
        return None
    hits=[]
    for other in range(3):
        if other == robot: continue
        reserved = _window(planned[other], start, end)
        if rank[other] < rank[robot]:
            high, low, h, r = reserved, local, other, robot
        else:
            high, low, h, r = local, reserved, robot, other
        # Actual physical clearance plus pair_conflict's >=0.001 mm margin.
        # The previous d version's 2x moving-robot guard is deliberately removed.
        for factor,moving_only in ((1.,False),):
            hit=pair_conflict(env.config,high,low,h,r,factor,moving_only)
            if hit is not None: hits.append(hit)
    return min(hits,key=lambda h:h.start,default=None)


def task_tail(env, current, task, home):
    local=[list(current)]
    env._move(local,task['a'],'T')
    env._move(local,task['b'],'D')
    escape=[list(local[-1])]
    env._move(escape,home,'T')
    trial=[list(row) for row in local]
    append_rows(trial,escape)
    return local,trial


def schedule(env, groups, z, priority_order):
    order=tuple(priority_order);rank={r:i for i,r in enumerate(order)}
    tasks=[]
    for owner,group in enumerate(groups):
        own=[]
        for i,(a,b) in enumerate(group):
            a=np.asarray([*a,z],dtype=np.float32).astype(float)
            b=np.asarray([*b,z],dtype=np.float32).astype(float)
            if np.linalg.norm(b-a)<=1e-6: continue
            own.append(dict(id=f'{owner}:{i}',owner=owner,a=a.tolist(),b=b.tolist()))
        tasks.append(own)
    planned=[[[0.,*home,'W']] for home in env.homes]
    deferred=[[],[],[]];executed=[];events=[];checks=0
    # The provisional escape to home certifies that accepting a task cannot
    # strand the robot in another robot's future trajectory.
    for robot in order:
        body=planned[robot]
        for task in tasks[robot]:
            local,trial=task_tail(env,body[-1],task,env.homes[robot])
            hit=conflict(env,trial,planned,robot,rank);checks+=1
            if hit is None:
                append_rows(body,local)
                executed.append(dict(task_id=task['id'],original_robot=robot+1,
                                     executing_robot=robot+1,phase='primary'))
                continue
            higher=[r for r in order[:rank[robot]] if all(
                np.linalg.norm(np.asarray(point[:2])-env.bases[r,:2]) <=
                env.robots[r].xy_reach_radius_mm-.0005 for point in (task['a'],task['b']))]
            recipient=higher[0] if higher else robot
            deferred[recipient].append(task)
            events.append(dict(task_id=task['id'],from_robot=robot+1,to_robot=recipient+1,
                               collision_time_s=hit.start,segment_start=task['a'],segment_end=task['b'],
                               reason='higher_priority_handoff' if higher else 'no_reachable_higher_keep_original'))
        env._move(body,env.homes[robot],'T')
    primary_makespan=max(r[-1][0] for r in planned)
    waits=[0.,0.,0.]
    # Fill queues are released as early as safely possible after the owner's
    # primary work. Other robots' reserved primary work is never cancelled.
    for robot in order:
        if not deferred[robot]: continue
        start=planned[robot][-1][0]
        relative=[[0.,*env.homes[robot],'W']]
        for task in deferred[robot]:
            env._move(relative,task['a'],'T');env._move(relative,task['b'],'D')
        env._move(relative,env.homes[robot],'T')
        release=start
        safe_release=max(start,max(planned[r][-1][0] for r in range(3) if r!=robot))+.01
        for attempt in range(18):
            local=[[start,*env.homes[robot],'W']]
            shifted=[[row[0]+release,*row[1:]] for row in relative]
            if release>start:
                local.extend(shifted)
            else:
                local=shifted
            hit=conflict(env,local,planned,robot,rank);checks+=1
            if hit is None: break
            if release>=safe_release:
                raise SchedulingInfeasible(f'Deferred R{robot+1} route intersects a parked robot; tasks retained')
            release=safe_release if attempt>=15 else min(safe_release,max(release+.002,hit.end+.002))
        else: raise SchedulingInfeasible('Deferred queue release search exhausted')
        append_rows(planned[robot],local)
        waits[robot]=release-start
        executed.extend(dict(task_id=t['id'],original_robot=t['owner']+1,
                             executing_robot=robot+1,phase='deferred') for t in deferred[robot])
    expected=Counter(t['id'] for own in tasks for t in own)
    if Counter(t['task_id'] for t in executed)!=expected:
        raise AssertionError('Deposition task omission or duplicate execution')
    required_length=sum(np.linalg.norm(np.array(t['b'])-t['a']) for own in tasks for t in own)
    actual_length=sum(np.linalg.norm(np.array(b[1:4])-a[1:4]) for own in planned
                      for a,b in zip(own,own[1:]) if a[4]=='D')
    if not np.isclose(required_length,actual_length,rtol=1e-8,atol=1e-5):
        raise AssertionError('Deposition length changed during handoff')
    duration=max(r[-1][0] for r in planned)
    for own in planned:
        if own[-1][0]<duration: own.append([duration,*own[-1][1:4],'W'])
    if first_conflict(env.config,planned): raise SchedulingInfeasible('Final physical collision check failed')
    if validate_trajectory_set(trajectory_from_rows(planned),env.config).violations:
        raise SchedulingInfeasible('Trajectory semantics failed')
    return planned,duration,dict(collision_certified=True,guard_protocol_certified=True,
        proximity_guard_factor=1.,collision_margin_mm=max(.001,4*env.config.collision.geometry_epsilon_mm),
        home_wait_fallbacks=0,local_wait_repairs=0,
        priority_wait_s=waits,primary_makespan_s=primary_makespan,
        deferred_queue_wait_s=waits,handoff_count=sum(e['from_robot']!=e['to_robot'] for e in events),
        deferred_count=len(events),retained_original_count=sum(e['from_robot']==e['to_robot'] for e in events),
        required_deposition_length_mm=float(required_length),executed_deposition_length_mm=float(actual_length),
        coverage_tasks_complete=True,task_count=sum(len(t) for t in tasks),
        primary_task_counts=[sum(t['executing_robot']==r+1 and t['phase']=='primary' for t in executed) for r in range(3)],
        final_task_counts=[sum(t['executing_robot']==r+1 for t in executed) for r in range(3)],
        handoffs=events,task_execution=executed,schedule_checks=checks,
        requested_layer_priority=[r+1 for r in order],effective_layer_priority=[r+1 for r in order],
        priority_fallback_used=False)
