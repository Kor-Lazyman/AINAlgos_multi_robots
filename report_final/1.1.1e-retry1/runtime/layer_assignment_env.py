"""1.1.1.e: projected placement, coordinate actions and conflict-task handoff."""
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
import math
import numpy as np
from gymnasium import spaces
from shapely.geometry import Point
import _base_layer_env as base
from handoff_scheduler import schedule
from positioning import PositionPlan

VERSION = '1.1.1.e-retry1'
ENVIRONMENT_SCHEMA = 'projected_xy_start_coordinate_retry_before_handoff_v2'
LAYER_PRIORITY_ORDERS = list(permutations((0, 1, 2)))
ACTION_NVECS = [8, 33, 33, 2, 33, 33, 2, 33, 33, 2, len(LAYER_PRIORITY_ORDERS)]
ACTION_DESCRIPTION = dict(hatch_angle='8 angles, 22.5 degree increments',
    robot_start_xy='Each robot selects x,y in a 33x33 layer-bounds grid; projected to nearest owned deposition segment',
    robot_direction='Each robot selects CCW/CW sweep from its selected deposition point',
    layer_priority='Action selects one of 6 robot priority permutations for this layer')
REACH_INSET_MM = 0.001  # Float32 CSV endpoint safety at circular boundaries.


@dataclass(frozen=True)
class LayerRewardWeights:
    """Compatibility object only: 1.1.1 has no reward weights."""
    pass


def priority_partition(segments, bases, radii):
    """Split at reach circles and nearest-base bisectors; retain every segment."""
    radii = np.asarray(radii, float)-REACH_INSET_MM
    groups = [[], [], []]
    for start, end in segments:
        a, b = np.asarray(start, float), np.asarray(end, float)
        delta = b-a
        aa = float(delta@delta)
        cuts = [0., 1.]
        for r in range(3):
            for s in range(r+1,3):
                # Equal squared distance is linear along this segment.
                normal=2*(bases[s,:2]-bases[r,:2])
                constant=float(bases[r,:2]@bases[r,:2]-bases[s,:2]@bases[s,:2])
                denominator=float(normal@delta)
                if abs(denominator)>1e-12:
                    t=-(float(normal@a)+constant)/denominator
                    if 0<t<1: cuts.append(t)
        for center, radius in zip(bases[:, :2], radii):
            q = a-center
            bb, cc = 2*float(q@delta), float(q@q)-radius**2
            disc = bb*bb-4*aa*cc
            if disc > 0 and aa > 0:
                cuts.extend(t for t in ((-bb-math.sqrt(disc))/(2*aa), (-bb+math.sqrt(disc))/(2*aa)) if 0<t<1)
        cuts = sorted(set(cuts))
        for lo, hi in zip(cuts, cuts[1:]):
            if (hi-lo)*math.sqrt(aa) < 1e-5:
                continue
            midpoint = a+(lo+hi)*0.5*delta
            owners = np.flatnonzero(np.linalg.norm(bases[:, :2]-midpoint, axis=1) <= radii+1e-8)
            if not len(owners):
                raise ValueError('STL path lies outside the union of all three safe reach regions')
            p, q = a+lo*delta, a+hi*delta
            owner=int(owners[np.argmin(np.linalg.norm(bases[owners,:2]-midpoint,axis=1))])
            groups[owner].append((tuple(p), tuple(q)))
    return groups


def order_from_start(group, robot, target, bases, radii, xy_action, direction):
    """Choose a point ON a deposited segment, not a bounding-box corner.

The selected segment is split at its midpoint so the robot starts exactly at
the chosen point while retaining both halves. A polar sweep learns CW/CCW.
"""
    if not group:
        return [], dict(start_xyz=None, start_region='empty', overlap_start_available=False)
    points = np.asarray(group, float)
    mids = points.mean(axis=1)
    center = np.asarray([target.centroid.x, target.centroid.y])
    lower=np.asarray(target.bounds[:2]);upper=np.asarray(target.bounds[2:])
    requested=lower+np.asarray(xy_action,dtype=float)/32*(upper-lower)
    delta=points[:,1]-points[:,0]
    fractions=np.clip(np.sum((requested-points[:,0])*delta,axis=1)/np.maximum(np.sum(delta*delta,axis=1),1e-15),0.,1.)
    projections=points[:,0]+fractions[:,None]*delta
    chosen=int(np.argmin(np.linalg.norm(projections-requested,axis=1)))
    start=projections[chosen]
    angles = np.arctan2(mids[:, 1]-center[1], mids[:, 0]-center[0])
    sign = -1 if direction else 1
    phase = np.mod(sign*(angles-angles[chosen]), 2*math.pi)
    remaining = (i for i in range(len(group)) if i != chosen)
    indices = sorted(remaining, key=lambda i: (phase[i], float(np.linalg.norm(mids[i]-start)), i))
    a, b = points[chosen]
    if direction:
        a, b = b, a
    ordered = [(tuple(start), tuple(b))]
    current = b
    for i in indices:
        p, q = points[i]
        if np.linalg.norm(q-current) < np.linalg.norm(p-current):
            p, q = q, p
        ordered.append((tuple(p), tuple(q)))
        current = q
    ordered.append((tuple(a), tuple(start)))
    ordered=[(a,b) for a,b in ordered if np.linalg.norm(np.asarray(b)-a)>1e-6]
    return ordered, dict(start_xy=start.tolist(),requested_start_xy=requested.tolist(),
                         start_xy_action=list(map(int,xy_action)),start_region='nearest_owned_segment',
                         chosen_segment=chosen,direction='CW' if direction else 'CCW')


class LayerPathEnv(base.LayerPathEnv):
    def _prepare_mesh(self, mesh):
        self.positioning = PositionPlan(mesh, self.config,
            Path(__file__).resolve().parent/'output'/'position_cache')
        return self.positioning.mesh

    def __init__(self, scenario, *, reward_weights=None):
        self._region_cache = {}
        self._segment_cache = {}
        super().__init__(scenario)
        self.action_space = spaces.MultiDiscrete(ACTION_NVECS)
        self.reward_weights = LayerRewardWeights()

    def regions(self, target):
        key = target.wkb
        if key not in self._region_cache:
            lo=np.asarray(target.bounds[:2]);hi=np.asarray(target.bounds[2:])
            grid=np.asarray([(x+.5,y+.5) for y in range(16) for x in range(16)])/16
            xy=lo+grid*(hi-lo)
            weights=np.asarray(self._raster(target));weights=weights/max(weights.sum(),1e-15)
            d2=np.sum((xy[:,None,:]-self.bases[None,:,:2])**2,axis=2)
            reach=d2<=np.asarray([r.xy_reach_radius_mm for r in self.robots])**2
            owners=np.argmin(np.where(reach,d2,np.inf),axis=1)
            self._region_cache[key]=dict(owned_fraction=np.bincount(owners,weights=weights,minlength=3).tolist(),
                triple_fraction=float(weights[reach.all(axis=1)].sum()),
                r2_r3_start_fraction=float(weights[reach[:,1]&reach[:,2]].sum()))
        return self._region_cache[key]

    def _observation(self):
        f = [self.index/len(self.layers), math.log1p(self.makespan)/20,
             math.log1p(self.last_duration)/20, *(math.log1p(v)/10 for v in self.last_robot_counts)]
        if self.index < len(self.layers):
            k, target = self.layers[self.index]
            region = self.regions(target)
            f += [self._z(k)/self.coord_scale, *(x/self.coord_scale for x in target.bounds),
                  target.area/self.coord_scale**2, target.length/self.coord_scale,
                  *region['owned_fraction'], region['triple_fraction'], region['r2_r3_start_fraction'],
                  *self._raster(target)]
        else:
            f += [0.]*(7+5+256)
        for r, robot in enumerate(self.robots):
            f += [*(self.bases[r]/self.coord_scale), *(self.homes[r]/self.coord_scale),
                  robot.xy_reach_radius_mm/self.coord_scale, robot.arm_envelope_radius_mm/self.coord_scale,
                  robot.tcp_radius_mm/self.coord_scale]
        p = self.config.process
        f += [p.bead_width_mm/self.coord_scale, p.layer_height_mm/self.coord_scale,
              p.deposition_speed_mm_s/self.coord_scale, p.travel_speed_mm_s/self.coord_scale]
        return np.asarray(f, np.float32)

    def _info(self, **extra):
        return dict(version=VERSION, environment=ENVIRONMENT_SCHEMA, completed_layers=self.index,
                    total_layers=len(self.layers), schedule_complete=self.index==len(self.layers),
                    makespan_s=self.makespan, **extra)

    def step(self, action):
        if self.done:
            raise RuntimeError('Episode ended; reset before stepping')
        if not self.action_space.contains(action):
            raise ValueError(f'Expected action in {ACTION_NVECS}')
        action = np.asarray(action, int)
        layer, target = self.layers[self.index]
        key = (target.wkb, int(action[0]))
        radii = np.asarray([r.xy_reach_radius_mm for r in self.robots])
        if key not in self._segment_cache:
            # Fixed bead spacing prevents reducing required work via a sparse-path action.
            geometry_action = [int(action[0]), 1, 0, 0, 0, 0, 0]
            segments = base.generate_layer_segments(target, self.config.process.bead_width_mm,
                self.config.shape_validation.polygon_buffer_resolution, geometry_action)
            groups = priority_partition(segments, self.bases, radii)
            self._segment_cache[key] = groups
        groups = self._segment_cache[key]
        ordered, starts = [], []
        for r in range(3):
            own, metadata = order_from_start(groups[r], r, target, self.bases, radii,
                                             action[1+3*r:3+3*r], int(action[3+3*r]))
            ordered.append(own)
            starts.append(metadata)
        priority_index = int(action[10])
        priority_order = LAYER_PRIORITY_ORDERS[priority_index]
        rows, duration, scheduling = schedule(self, ordered, self._z(layer), priority_order)
        for robot,own in enumerate(rows):
            first=next((row for row in own[:-1] if row[4]=='D'),None)
            starts[robot]['actual_first_deposition_xyz']=list(first[1:4]) if first is not None else None
        self.latest_layer_rows = rows
        offset = self.makespan
        for r, own in enumerate(rows):
            self.rows[r][-1][4] = own[0][4]
            self.rows[r].extend([[row[0]+offset, *row[1:]] for row in own[1:]])
        self.makespan += duration
        self.index += 1
        self.done = self.index == len(self.layers)
        self.last_duration = duration
        self.last_robot_counts = scheduling['final_task_counts']
        activity = [{mode: sum(b[0]-a[0] for a,b in zip(own, own[1:]) if a[4]==mode)
                     for mode in ('D','T','W')} for own in rows]
        utilization = [(r['D']+r['T'])/duration for r in activity]
        reward = -float(duration)
        info = self._info(layer_index=layer, layer_duration_s=duration, reward=reward,
            robot_segment_counts=self.last_robot_counts, robot_utilization=utilization,
            robot_deposition_utilization=[r['D']/duration for r in activity],
            robot_wait_s=[r['W'] for r in activity], mean_robot_utilization=float(np.mean(utilization)),
            starting_points=starts, layer_priority=[r+1 for r in priority_order],
            ownership=self.regions(target), **scheduling)
        self.layer_history.append(dict(action=action.tolist(), **info))
        return self._observation(), reward, self.done, False, info

    @staticmethod
    def decode_action(action):
        action=np.asarray(action)
        return dict(hatch_angle_deg=int(action[0])*22.5,
                    start_xy_grid=[action[1+3*r:3+3*r].tolist() for r in range(3)],
                    directions=['CW' if action[3+3*r] else 'CCW' for r in range(3)],
                    layer_priority=[r+1 for r in LAYER_PRIORITY_ORDERS[int(action[10])]])

    def export(self, output):
        output=super().export(output)
        self.positioning.export(output)
        return output


class MultiLayerEnv(base.MultiLayerEnv):
    def step(self, action):
        current=self.environments[self.active]
        self.latest_attempt=dict(scenario=current.scenario.name,layer=current.index+1,
                                 action=np.asarray(action).tolist())
        print(f"LAYER job={current.scenario.name} layer={current.index+1}/{len(current.layers)} action={np.asarray(action).tolist()}",flush=True)
        result = super().step(action)
        # Retain the completed layer across DummyVecEnv's automatic reset.
        env = self.environments[self.active]
        self.latest_gantt = dict(rows=env.latest_layer_rows, scenario=env.scenario.name,
                                 layer=env.index)
        return result

    def get_latest_gantt(self):
        return self.latest_gantt

    def __init__(self, scenarios, *, reward_weights=None):
        # Construct our version explicitly, without changing base-module globals.
        import gymnasium as gym
        gym.Env.__init__(self)
        self.scenarios = [Path(p).resolve() for p in scenarios]
        if not self.scenarios:
            raise ValueError('No training jobs')
        self.environments = []
        for scenario in self.scenarios:
            print(f'Slicing 1.1.1 training STL {scenario.name}', flush=True)
            self.environments.append(LayerPathEnv(scenario))
        self.action_space = self.environments[0].action_space
        self.observation_space = self.environments[0].observation_space
        self.reward_weights = LayerRewardWeights()
        self.episode_counts = [0]*len(self.scenarios)
        self.step_counts = [0]*len(self.scenarios)
        self.active, self._cycle = None, []
