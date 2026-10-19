"""1.0.2: one action generates and schedules an entire STL layer.

The policy controls path parameters and three-robot partitioning. Geometry is
sliced once; deposition paths are generated at step time, not loaded as tasks.
All robots return home at each layer barrier, allowing local collision checks.
The complete exported trajectory is still checked by the official Validator.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import tempfile

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from shapely import LineString, box
from shapely.affinity import rotate

from validator_adapter import load_config, run_validation, parts, trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.errors import WaamValidatorError
from waam_validator.shape.deposition import build_deposited_layers
from waam_validator.shape.metrics import compute_shape_metrics
from waam_validator.shape.polygon_utils import normalize_polygon
from waam_validator.shape.target import determine_evaluation_layers, load_target_mesh, slice_target_layers
from waam_validator.trajectory.validator import validate_trajectory_set

VERSION = "1.0.2"
ENVIRONMENT_SCHEMA = "layer_path_v1"
ACTION_NVECS = [8, 3, 4, 2, 2, 3, 6]
SPACING_FACTORS = (0.8, 0.9, 1.0)
ROBOT_ORDERS = tuple(itertools.permutations(range(3)))
QUOTAS = ((1/3, 1/3, 1/3), (0.5, 0.25, 0.25), (0.25, 0.25, 0.5))
ACTION_DESCRIPTION = {
    "hatch_angle": "0..7 -> 0,22.5,...,157.5 degrees",
    "hatch_spacing": "0..2 -> bead width * (0.8,0.9,1.0)",
    "start_corner": "0..3 -> min/min, max/min, min/max, max/max XY",
    "reverse": "reverse segment sequence and directions",
    "partition_axis": "0=X, 1=Y; spatial bands weighted by deposition length",
    "partition_quota": "equal, first-band-heavy, last-band-heavy",
    "robot_order": "lexicographic permutations of robot IDs 1,2,3",
}


@dataclass(frozen=True)
class LayerRewardWeights:
    iou: float = 1.0
    time: float = 0.1
    invalid: float = 2.0
    completion: float = 1.0
    validation_failure: float = 1.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("Reward weights must be finite and nonnegative")


def robot_layer_utilization(rows, duration):
    """Fraction of each robot's layer makespan spent travelling or depositing.

    A row's mode applies until the next row. W intervals, including the final
    barrier wait, are idle. All three robots share the same layer makespan.
    """
    if duration <= 0:
        return [0.0 for _ in rows]
    return [min(1.0, max(0.0, sum(
        max(0.0, next_row[0] - row[0]) for row, next_row in zip(own, own[1:])
        if row[4] in ("T", "D")) / duration)) for own in rows]


def generate_layer_segments(target, beadwidth, resolution, action, max_segment_mm=80.0):
    """Generate inset contours and clipped hatch from the actual policy action."""
    angle = int(action[0]) * 22.5
    spacing = beadwidth * SPACING_FACTORS[int(action[1])]
    origin = (0.0, 0.0)
    rotated = rotate(target, -angle, origin=origin)
    inset = rotated.buffer(-0.49 * beadwidth, quad_segs=resolution)
    if inset.is_empty:
        raise ValueError("No printable inset at the configured bead width")
    lines = []
    for polygon in parts(inset, "Polygon"):
        polygon = polygon.simplify(beadwidth * 0.01, preserve_topology=True)
        lines.extend([LineString(polygon.exterior.coords),
                      *(LineString(ring.coords) for ring in polygon.interiors)])
        xmin, ymin, xmax, ymax = polygon.bounds
        count = max(1, math.ceil((ymax-ymin) / spacing))
        for row, y in enumerate(np.linspace(ymin, ymax, count+1)):
            clipped = polygon.intersection(LineString([(xmin-beadwidth, y), (xmax+beadwidth, y)]))
            for line in parts(clipped, "LineString"):
                lines.append(LineString(list(line.coords)[::-1]) if row % 2 else line)
    segments = []
    for line in lines:
        coords = list(rotate(line, angle, origin=origin).coords)
        for start, end in zip(coords, coords[1:]):
            a, b = np.asarray(start[:2]), np.asarray(end[:2])
            distance = float(np.linalg.norm(b-a))
            if distance <= 1e-5:
                continue
            count = max(1, math.ceil(distance / max_segment_mm))
            for i in range(count):
                # Match official CSV loading precision before reach/timing checks.
                p, q = (np.asarray(a+(b-a)*t/count, dtype=np.float32).astype(float)
                        for t in (i, i+1))
                if np.linalg.norm(q-p) > 1e-5:
                    segments.append((tuple(p), tuple(q)))
    if not segments:
        raise ValueError("Layer generated no deposition segments")
    xmin, ymin, xmax, ymax = target.bounds
    corner = int(action[2])
    anchor = np.asarray((xmax if corner & 1 else xmin, ymax if corner & 2 else ymin))
    start = min(range(len(segments)), key=lambda i: (np.linalg.norm(np.asarray(segments[i][0])-anchor), i))
    segments = segments[start:] + segments[:start]
    if int(action[3]):
        segments = [(b, a) for a, b in reversed(segments)]
    return segments


class LayerPathEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, scenario, *, reward_weights=None):
        super().__init__()
        self.scenario = Path(scenario).resolve()
        self.config = load_config(self.scenario / "config.yaml")
        self.reward_weights = reward_weights or LayerRewardWeights()
        self.mesh = load_target_mesh(self.scenario / "target.stl", self.config)
        if hasattr(self, "_prepare_mesh"):
            self.mesh = self._prepare_mesh(self.mesh)
        raw = slice_target_layers(self.mesh, determine_evaluation_layers(self.mesh, {}, self.config), self.config)
        s = self.config.shape_validation
        self.layers = [(k, normalize_polygon(v, s.polygon_snap_tolerance_mm, s.area_epsilon_mm2))
                       for k, v in sorted(raw.items()) if not v.is_empty and v.area > s.area_epsilon_mm2]
        if not self.layers:
            raise ValueError("STL has no printable layers")
        self.target_layers = dict(self.layers)
        self.total_target_area = sum(g.area for _, g in self.layers)
        self.robots = sorted(self.config.robots, key=lambda r: r.id)
        self.homes = np.asarray([r.home_xyz_mm if r.home_xyz_mm is not None else r.base_xyz_mm
                                 for r in self.robots], dtype=np.float32).astype(float)
        self.bases = np.asarray([r.base_xyz_mm for r in self.robots], dtype=float)
        self.coord_scale = max(1.0, float(np.abs(self.mesh.bounds).max()), float(np.abs(self.homes).max()),
                               float(np.abs(self.bases).max()))
        self.action_space = spaces.MultiDiscrete(ACTION_NVECS)
        self._raster_cache = {}
        self.reset()
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=self._observation().shape, dtype=np.float32)
        parked = self._trajectory([[list(row), [1e-6, *row[1:]]] for row in [s[0] for s in self.rows]])
        if validate_trajectory_set(parked, self.config).violations or run_collision_analysis(parked, self.config).events:
            raise ValueError("Initial home positions violate reach/collision constraints")

    _trajectory = staticmethod(trajectory_from_rows)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.rows = [[[0.0, *home, "W"]] for home in self.homes]
        self.index = 0
        self.done = False
        self.makespan = 0.0
        self.current_iou = 0.0
        self.last_layer_iou = 0.0
        self.last_duration = 0.0
        self.last_robot_counts = [0, 0, 0]
        self.deposited_area = self.intersection_area = 0.0
        self.layer_history = []
        self.terminal_validation = None
        self.terminal_validation_artifacts = None
        return self._observation(), self._info()

    def _raster(self, target):
        key = target.wkb
        if key not in self._raster_cache:
            xmin, ymin, xmax, ymax = target.bounds
            dx, dy = (xmax-xmin)/16, (ymax-ymin)/16
            self._raster_cache[key] = [target.intersection(box(xmin+x*dx, ymin+y*dy,
                                                             xmin+(x+1)*dx, ymin+(y+1)*dy)).area/(dx*dy)
                                       for y in range(16) for x in range(16)]
        return self._raster_cache[key]

    def _observation(self):
        features = [self.index/len(self.layers), math.log1p(len(self.layers))/10,
                    self.current_iou, self.last_layer_iou, math.log1p(self.makespan)/20,
                    math.log1p(self.last_duration)/20,
                    *(math.log1p(v)/10 for v in self.last_robot_counts)]
        if self.index < len(self.layers):
            layer, target = self.layers[self.index]
            features.extend([self._z(layer)/self.coord_scale, *(v/self.coord_scale for v in target.bounds),
                             target.area/self.coord_scale**2, target.length/self.coord_scale])
            features.extend(self._raster(target))
        else:
            features.extend([0.0]*(7+256))
        for r, robot in enumerate(self.robots):
            features.extend([*(self.bases[r]/self.coord_scale), *(self.homes[r]/self.coord_scale),
                             robot.xy_reach_radius_mm/self.coord_scale,
                             robot.arm_envelope_radius_mm/self.coord_scale,
                             robot.tcp_radius_mm/self.coord_scale])
        p, s = self.config.process, self.config.shape_validation
        features.extend([p.bead_width_mm/self.coord_scale, p.layer_height_mm/self.coord_scale,
                         p.travel_speed_mm_s/self.coord_scale, p.deposition_speed_mm_s/self.coord_scale,
                         self.config.collision.arm_clearance_mm/self.coord_scale,
                         s.minimum_overall_coverage, s.maximum_overall_overfill_ratio,
                         s.minimum_overall_iou, s.minimum_layer_iou, s.maximum_failed_layer_ratio])
        return np.asarray(features, dtype=np.float32)

    def _z(self, layer):
        p = self.config.process
        return float(np.float32(p.build_plane_z_mm+(layer+(1 if p.tcp_z_reference == "top" else 0.5))*p.layer_height_mm))

    def _info(self, **extra):
        return dict(version=VERSION, environment=ENVIRONMENT_SCHEMA, completed_layers=self.index,
                    total_layers=len(self.layers), schedule_complete=self.index == len(self.layers),
                    makespan_s=self.makespan, iou=self.current_iou, **extra)

    def reachable_robots(self, start, end):
        return tuple(r for r, robot in enumerate(self.robots)
                     if all(np.linalg.norm(np.asarray(p[:2])-self.bases[r, :2]) <=
                            robot.xy_reach_radius_mm+self.config.collision.geometry_epsilon_mm
                            for p in (start, end)))

    def _partition(self, segments, action):
        axis = int(action[4])
        order = ROBOT_ORDERS[int(action[6])]
        lengths = np.asarray([np.linalg.norm(np.asarray(b)-a) for a, b in segments])
        spatial = sorted(range(len(segments)), key=lambda i: ((segments[i][0][axis]+segments[i][1][axis])/2, i))
        limits = np.cumsum(QUOTAS[int(action[5])])*float(lengths.sum())
        requested = {}
        progress = 0.0
        for i in spatial:
            band = min(2, int(np.searchsorted(limits, progress+lengths[i]/2, side="right")))
            requested[i] = order[band]
            progress += lengths[i]
        groups = [[], [], []]
        loads = [0.0, 0.0, 0.0]
        reassigned = 0
        for i, (a, b) in enumerate(segments):
            reachable = self.reachable_robots(a, b)
            if not reachable:
                return None, reassigned
            robot = requested[i]
            if robot not in reachable:
                robot = min(reachable, key=lambda r: (loads[r], r))
                reassigned += 1
            groups[robot].append((a, b))
            loads[robot] += lengths[i]
        return groups, reassigned

    def _move(self, rows, point, mode):
        point = np.asarray(point, dtype=np.float32).astype(float)
        distance = float(np.linalg.norm(point-np.asarray(rows[-1][1:4])))
        if distance <= 1e-6:
            return
        speed = self.config.process.deposition_speed_mm_s if mode == "D" else self.config.process.travel_speed_mm_s
        rows[-1][4] = mode
        rows.append([rows[-1][0]+distance/speed, *point, "W"])

    def step(self, action):
        raise NotImplementedError('Use layer_assignment_env.LayerPathEnv for d pause/resume scheduling')

    @staticmethod
    def decode_action(action):
        return dict(hatch_angle_deg=int(action[0])*22.5, spacing_factor=SPACING_FACTORS[int(action[1])],
                    start_corner=int(action[2]), reverse=bool(action[3]), partition_axis="xy"[int(action[4])],
                    quotas=list(QUOTAS[int(action[5])]), robot_order=[r+1 for r in ROBOT_ORDERS[int(action[6])]])

    def export(self, output):
        if self.index != len(self.layers):
            raise RuntimeError("Cannot export an incomplete layer schedule")
        output = Path(output)
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Choose a new/empty output directory")
        output.mkdir(parents=True, exist_ok=True)
        for name in ("config.yaml", "target.stl"):
            shutil.copy2(self.scenario/name, output/name)
        with (output/"trajectory.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["robot_id", "time_s", "x_mm", "y_mm", "z_mm", "mode"])
            for r, own in enumerate(self.rows, 1):
                writer.writerows([[r, *row] for row in own])
        return output


class MultiLayerEnv(gym.Env):
    def __init__(self, scenarios, *, reward_weights=None):
        super().__init__()
        self.scenarios = [Path(p).resolve() for p in scenarios]
        if not self.scenarios:
            raise ValueError("No training scenarios")
        self.environments = []
        for scenario in self.scenarios:
            print(f"Slicing training STL {scenario.name} ...", flush=True)
            self.environments.append(LayerPathEnv(scenario, reward_weights=reward_weights))
        self.action_space = self.environments[0].action_space
        self.observation_space = self.environments[0].observation_space
        self.reward_weights = self.environments[0].reward_weights
        self.episode_counts = [0]*len(self.scenarios)
        self.step_counts = [0]*len(self.scenarios)
        self.active = None
        self._cycle = []

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._cycle = []
        if not self._cycle:
            self._cycle = list(self.np_random.permutation(len(self.environments)))
        self.active = int(self._cycle.pop())
        self.episode_counts[self.active] += 1
        observation, info = self.environments[self.active].reset(seed=int(self.np_random.integers(2**32)))
        return observation, dict(info, scenario_id=self.scenarios[self.active].name)

    def step(self, action):
        if self.active is None:
            raise RuntimeError("Call reset() before step()")
        observation, reward, terminated, truncated, info = self.environments[self.active].step(action)
        self.step_counts[self.active] += 1
        return observation, reward, terminated, truncated, dict(info, scenario_id=self.scenarios[self.active].name)

    def close(self):
        for env in self.environments:
            env.close()
