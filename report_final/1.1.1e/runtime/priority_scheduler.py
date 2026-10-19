"""Fixed-priority planning. Retain every move, repair conflicts with W intervals.

Collision checks cover the entire piecewise-linear time interval, not just its
samples: a distance lower bound certifies an interval, otherwise it is bisected.
Unresolved near-contact intervals are conservatively considered unsafe.
"""
from dataclasses import dataclass
import time
import numpy as np
from validator_adapter import trajectory_from_rows
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch
from waam_validator.trajectory.validator import validate_trajectory_set


class SchedulingInfeasible(RuntimeError):
    """No safe wait-only plan exists; never turn this into a cheap RL termination."""


@dataclass(frozen=True)
class Conflict:
    start: float
    end: float
    higher: int
    lower: int


def positions(rows, times):
    rows = np.asarray([r[:4] for r in rows], dtype=float)
    return np.column_stack([np.interp(times, rows[:, 0], rows[:, k]) for k in (1, 2, 3)])


def pair_conflict(config, rows_a, rows_b, a, b, distance_factor=1.0, moving_lower_only=False):
    """Earliest conservative contact, located to 0.1 ms continuously in XY.

    Midpoint margin minus summed endpoint displacements certifies the entire
    interval. Search uncertain intervals chronologically, so a long primitive
    crossing is stopped near entry, not at the beginning of the full primitive.
    """
    robots=sorted(config.robots,key=lambda robot:robot.id)
    ra,rb=robots[a],robots[b];c=config.collision
    knots=np.unique([r[0] for r in rows_a]+[r[0] for r in rows_b])
    if len(knots)<2: knots=np.array([knots[0],knots[0]+1e-6])
    left,right=knots[:-1],knots[1:]
    if moving_lower_only:
        times=np.array([row[0] for row in rows_b])
        idx=np.clip(np.searchsorted(times,(left+right)/2,side='right')-1,0,len(rows_b)-1)
        moving=np.array([rows_b[i][4] in ('T','D') and i<len(rows_b)-1 for i in idx])
        left,right=left[moving],right[moving]
    clearance=max(0.001,c.geometry_epsilon_mm*4)
    arr_a=np.asarray([row[:4] for row in rows_a],float)
    arr_b=np.asarray([row[:4] for row in rows_b],float)
    def interpolate(array, times):
        return np.column_stack([np.interp(times,array[:,0],array[:,k]) for k in (1,2,3)])
    def safe(lo,hi):
        a0,a1=interpolate(arr_a,lo),interpolate(arr_a,hi)
        b0,b1=interpolate(arr_b,lo),interpolate(arr_b,hi)
        am,bm=(a0+a1)/2,(b0+b1)/2
        margin=np.full(len(lo),np.inf)
        if c.check_arm_envelope:
            arm=check_arm_envelope_xy_batch(np.asarray(ra.base_xyz_mm[:2]),am[:,:2],
                ra.arm_envelope_radius_mm,np.asarray(rb.base_xyz_mm[:2]),bm[:,:2],
                rb.arm_envelope_radius_mm,c.arm_clearance_mm,c.geometry_epsilon_mm,c.touching_is_collision)
            margin=np.minimum(margin,arm.centerline_distance_mm-distance_factor*arm.required_distance_mm)
        if c.check_tcp_radius:
            margin=np.minimum(margin,np.linalg.norm(am[:,:2]-bm[:,:2],axis=1)
                              -distance_factor*(ra.tcp_radius_mm+rb.tcp_radius_mm))
        bound=(np.linalg.norm(a1[:,:2]-a0[:,:2],axis=1)+np.linalg.norm(b1[:,:2]-b0[:,:2],axis=1))/2
        return margin-bound>clearance
    def search(lo,hi,depth=0):
        if safe(np.array([lo]),np.array([hi]))[0]: return None
        if hi-lo<=1e-4 or depth>=24: return Conflict(float(lo),float(hi),a,b)
        mid=(lo+hi)/2
        return search(lo,mid,depth+1) or search(mid,hi,depth+1)
    uncertain=~safe(left,right)
    for lo,hi in zip(left[uncertain],right[uncertain]):
        hit=search(lo,hi)
        if hit is not None:return hit
    return None


def first_conflict(config, rows, pairs=None):
    pairs = pairs if pairs is not None else ((0, 1), (0, 2), (1, 2))
    events = [pair_conflict(config, rows[a], rows[b], a, b) for a, b in pairs]
    return min((e for e in events if e is not None), key=lambda e: (e.start, e.lower), default=None)


def insert_wait(route, index, delay):
    """Insert stationary W before a primitive. Preserve all T/D primitives."""
    if delay <= 0:
        raise ValueError('Wait duration must be positive')
    result = [list(row) for row in route[:index+1]]
    anchor = list(route[index])
    result[-1][4] = 'W'
    anchor[0] += delay
    result.append(anchor)
    result.extend([[row[0]+delay, *row[1:]] for row in route[index+1:]])
    return result


GUARD_FACTOR = 2.0


def _issues(config, rows, pairs):
    """A moving lower-priority robot must stay outside the 2x guard.

    While it waits, the higher-priority robot may pass inside the guard,
    but the original 1x physical clearance must hold continuously.
    """
    events = []
    for h, r in pairs:
        events.append(pair_conflict(config, rows[h], rows[r], h, r))
        events.append(pair_conflict(config, rows[h], rows[r], h, r,
                                    GUARD_FACTOR, moving_lower_only=True))
    return min((e for e in events if e is not None), key=lambda e:e.start, default=None)


def insert_wait_at(route, when, delay):
    """Pause within a primitive without losing or changing deposition geometry."""
    times = np.array([row[0] for row in route])
    i = min(len(route)-2, max(0, int(np.searchsorted(times, when, side='right')-1)))
    if abs(when-times[i]) < 1e-8:
        return insert_wait(route, i, delay)
    xyz = positions(route, np.array([when]))[0]
    split = [list(row) for row in route[:i+1]]
    split.append([float(when), *xyz, route[i][4]])
    split.extend([list(row) for row in route[i+1:]])
    return insert_wait(split, i+1, delay)


def _anchors(route, conflict_start):
    # Include an interior stop point, then retreat to earlier safe waypoints.
    # Extra points within long primitives avoid unnecessarily waiting at home.
    last = max(0., conflict_start-0.002)
    candidates = {last, 0.}
    for a,b in zip(route,route[1:]):
        if a[0] > last: break
        if a[4] == 'W': continue
        finish = min(last,b[0])
        length = np.linalg.norm(np.array(b[1:4])-a[1:4])
        count = max(1,int(np.ceil(length/50)))
        candidates.update(float(t) for t in np.linspace(a[0],b[0],count+1) if t<=finish)
    return sorted(candidates,reverse=True)


def _releases(config, planned, scheduled, route, r, anchor, release_knots):
    """Reject obstructed waits and in-guard release times before route searches."""
    point=positions(route,np.array([anchor]))[0]
    limit=max(planned[h][-1][0] for h in scheduled)+0.01
    for h in scheduled:
        times=np.unique([anchor,limit]+[row[0] for row in planned[h] if anchor<row[0]<limit])
        high=[[float(t),*pt,'T'] for t,pt in zip(times,positions(planned[h],times))]
        hold=[[anchor,*point,'W'],[limit,*point,'W']]
        hit=pair_conflict(config,high,hold,h,r)
        if hit is not None: limit=min(limit,hit.start-0.002)
        if limit<=anchor: return []
    releases=np.array([t+0.002 for t in release_knots if anchor<t+0.002<=limit])
    if not len(releases): return []
    robots=sorted(config.robots,key=lambda robot:robot.id)
    lower=robots[r];c=config.collision
    valid=np.ones(len(releases),dtype=bool)
    low=np.tile(point,(len(releases),1))
    for h in scheduled:
        high=positions(planned[h],releases);upper=robots[h]
        if c.check_tcp_radius:
            valid &= np.linalg.norm(high[:,:2]-low[:,:2],axis=1)>GUARD_FACTOR*(upper.tcp_radius_mm+lower.tcp_radius_mm)+0.001
        if c.check_arm_envelope:
            arm=check_arm_envelope_xy_batch(np.asarray(upper.base_xyz_mm[:2]),high[:,:2],upper.arm_envelope_radius_mm,
                np.asarray(lower.base_xyz_mm[:2]),low[:,:2],lower.arm_envelope_radius_mm,c.arm_clearance_mm,
                c.geometry_epsilon_mm,c.touching_is_collision)
            valid &= arm.centerline_distance_mm>GUARD_FACTOR*arm.required_distance_mm+0.001
    return releases[valid].tolist()


def _window(route, start, end):
    """Clip time only; retain the movement mode on each clipped primitive."""
    times=np.asarray([row[0] for row in route])
    idx=min(len(route)-1,max(0,int(np.searchsorted(times,start,side='right')-1)))
    endpoints=positions(route,np.array([start,end]))
    result=[[start,*endpoints[0],route[idx][4]]]
    result.extend([list(row) for row in route if start<row[0]<end])
    result.append([end,*endpoints[1],'W'])
    return result


def _resume_clear(config, planned, pairs, candidate, r, anchor, end):
    # The unchanged prefix is already certified. Check only the inserted wait
    # and required advance; later conflicts are handled on the next iteration.
    local=list(planned)
    local[r]=_window(candidate,anchor,end)
    for h,_ in pairs: local[h]=_window(planned[h],anchor,end)
    return _issues(config,local,pairs) is None


def schedule(env, routes, priority_order=(0,1,2), max_repairs=256):
    """Offline look-ahead pause/resume controller with fixed layer precedence.

    No whole-route serial fallback, no priority swap, no route removal. If
    wait-only control cannot produce a safe schedule, raise an explicit error.
    """
    order = tuple(int(r) for r in priority_order)
    if sorted(order) != [0,1,2]: raise ValueError('Invalid robot priority permutation')
    planned = [[list(row) for row in route] for route in routes]
    waits = [0.,0.,0.]
    events = []
    scheduled = []
    last_progress=time.perf_counter()
    for r in order:
        route = planned[r]
        pairs = [(h,r) for h in scheduled]
        if len(route)<2:
            scheduled.append(r)
            continue
        for repair in range(max_repairs+1):
            if time.perf_counter()-last_progress>30:
                print(f'SCHEDULER R{r+1} repair={repair} waits={waits}',flush=True)
                last_progress=time.perf_counter()
            planned[r] = route
            issue = _issues(env.config,planned,pairs)
            if issue is None: break
            if repair == max_repairs:
                raise SchedulingInfeasible(f'R{r+1}: local pause budget exhausted; no serial fallback')
            # Require meaningful path progress while still allowing multiple
            # stops inside a long primitive. Clearing an entire long primitive
            # at once can rule out valid local stop/resume solutions.
            idx=min(len(route)-2,max(0,int(np.searchsorted([row[0] for row in route],issue.start,side='right')-1)))
            a,b=route[idx],route[idx+1]
            speed=np.linalg.norm(np.array(b[1:4])-a[1:4])/max(b[0]-a[0],1e-9)
            progress_target=min(b[0],issue.end+10./speed) if speed>1e-9 else b[0]
            advanced = False
            # Search the nearest viable stopping location first. Predict the
            # higher route during the entire wait: a stopped arm is not invisible.
            release_knots = sorted(set(row[0] for h in scheduled for row in planned[h]
                                       if row[0]>issue.start))
            for anchor in _anchors(route,issue.start):
                last_delay = 0.
                for release in _releases(env.config,planned,scheduled,route,r,anchor,release_knots):
                    delay = max(0.002, release-anchor)
                    candidate = insert_wait_at(route,anchor,delay)
                    # Measure progress in original route time, not the shifted
                    # wall clock. Repeated delay of the same conflict is not progress.
                    good = _resume_clear(env.config,planned,pairs,candidate,r,anchor,progress_target+delay)
                    if good:
                        lo,hi = last_delay,delay
                        for _ in range(10):
                            mid=(lo+hi)/2
                            test=insert_wait_at(route,anchor,mid)
                            if _resume_clear(env.config,planned,pairs,test,r,anchor,progress_target+mid):
                                hi=mid; candidate=test
                            else: lo=mid
                        delay=hi
                        route=candidate
                        waits[r]+=delay
                        events.append(dict(robot=r+1,higher_robot=issue.higher+1,
                            trigger_time_s=issue.start,stop_time_s=anchor,
                            resume_time_s=anchor+delay,wait_s=delay,
                            stop_xyz_mm=positions(route,np.array([anchor]))[0].tolist()))
                        advanced=True
                        break
                    last_delay=delay
                    # The chosen stopped position is physically obstructing a
                    # higher robot. Longer waits cannot fix that: retreat anchor.
                    wait_rows=[[anchor,*positions(route,np.array([anchor]))[0],'W'],
                               [anchor+delay,*positions(route,np.array([anchor]))[0],'W']]
                    obstructed=False
                    for h in scheduled:
                        times=sorted(set([anchor,anchor+delay]+[x[0] for x in planned[h]
                                          if anchor<x[0]<anchor+delay]))
                        xyz=positions(planned[h],np.array(times))
                        high=[[t,*pt,'T'] for t,pt in zip(times,xyz)]
                        if pair_conflict(env.config,high,wait_rows,h,r):
                            obstructed=True;break
                    if obstructed: break
                if advanced: break
            if not advanced:
                raise SchedulingInfeasible(f'R{r+1}: no safe local stop/resume at t={issue.start:.6f}; '
                                           'routes retained, no serial fallback')
        planned[r]=route
        scheduled.append(r)
    duration=max(route[-1][0] for route in planned)
    for own in planned:
        if own[-1][0]<duration: own.append([duration,*own[-1][1:4],'W'])
    if first_conflict(env.config,planned):
        raise SchedulingInfeasible('Final 1x continuous collision check failed')
    all_pairs=[(h,r) for i,h in enumerate(order) for r in order[i+1:]]
    if _issues(env.config,planned,all_pairs):
        raise SchedulingInfeasible('Final 2x moving-lower guard check failed')
    messages=validate_trajectory_set(trajectory_from_rows(planned),env.config)
    if messages.violations: raise SchedulingInfeasible(f'Trajectory semantics: {messages.violations}')
    return planned,duration,dict(priority_wait_s=waits,local_wait_repairs=len(events),
        home_wait_fallbacks=0,collision_certified=True,proximity_guard_factor=GUARD_FACTOR,
        guard_protocol_certified=True,pause_events=events,
        requested_layer_priority=[r+1 for r in order],effective_layer_priority=[r+1 for r in order],
        priority_fallback_used=False)
