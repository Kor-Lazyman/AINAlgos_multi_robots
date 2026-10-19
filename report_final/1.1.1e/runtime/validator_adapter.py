"""Use only the Validator source bundled with this independent version."""
from pathlib import Path
import sys
import numpy as np

VALIDATOR_ROOT = Path(__file__).resolve().parent / 'environment'
sys.path.insert(0, str(VALIDATOR_ROOT / 'src'))
from waam_validator import load_config, run_validation
from waam_validator.models import RobotTrajectory, TrajectorySet


def parts(geometry, kind):
    if geometry.is_empty:
        return
    if geometry.geom_type == kind:
        yield geometry
    elif hasattr(geometry, 'geoms'):
        for component in geometry.geoms:
            yield from parts(component, kind)


def trajectory_from_rows(rows):
    trajectories = []
    for robot, source in enumerate(rows, 1):
        source = [list(row) for row in source]
        if len(source) == 1:
            source.append([source[0][0] + 1e-6, *source[0][1:4], 'W'])
        trajectories.append(RobotTrajectory(robot,
            np.array([r[0] for r in source], dtype=np.float64),
            np.array([r[1:4] for r in source], dtype=np.float32),
            np.array([{'T': 0, 'D': 1, 'W': 2}[r[4]] for r in source], dtype=np.uint8)))
    return TrajectorySet(tuple(trajectories), sum(len(t.time_s) for t in trajectories))
