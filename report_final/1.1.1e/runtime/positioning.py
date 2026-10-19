"""Balance equal-weight solid samples projected to XY before slicing."""
from pathlib import Path
import hashlib
import json
import numpy as np
from shapely import union_all
from shapely.affinity import translate
from shapely.geometry import Point,MultiPoint
from solid_sampling import solid_points

SCHEMA='nearest_reachable_projected_point_balanced_position_v3'
INSET=.01


class PositionPlan:
    """Optimize one STL XY offset for nearest reachable initial ownership."""
    def __init__(self,mesh,config,cache_dir):
        digest=hashlib.sha256(mesh.vertices.tobytes()+mesh.faces.tobytes()+
            config.model_dump_json().encode()+SCHEMA.encode()).hexdigest()
        cache=Path(cache_dir)/digest;cache.mkdir(parents=True,exist_ok=True)
        planfile=cache/'position.json'
        if planfile.is_file(): self.report=json.loads(planfile.read_text(encoding='utf-8'))
        else:
            self.report=self._solve(mesh,config)
            planfile.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        self.mesh=mesh.copy();self.mesh.apply_translation(self.report['translation_xyz_mm'])
        self.cache_dir=cache

    @staticmethod
    def _solve(mesh,config):
        robots=sorted(config.robots,key=lambda r:r.id)
        bases=np.asarray([r.base_xyz_mm for r in robots],float)
        radii=np.asarray([r.xy_reach_radius_mm for r in robots],float)
        points,spacing=solid_points(mesh)
        xy,multiplicity=np.unique(points[:,:2],axis=0,return_counts=True)
        scale=float(max(radii)**2)
        workspace=Point(*config.workspace.center_xy_mm).buffer(config.workspace.radius_mm,quad_segs=256)
        safe_workspace=workspace.buffer(-config.process.bead_width_mm/2-INSET)
        reach_disks=[Point(*b[:2]).buffer(r-INSET,quad_segs=256) for b,r in zip(bases,radii)]
        reach_union=union_all(reach_disks)
        hull=MultiPoint(mesh.vertices[:,:2]).convex_hull
        center=np.asarray(config.workspace.center_xy_mm,float)
        mesh_center=(mesh.bounds[0,:2]+mesh.bounds[1,:2])/2
        aligned=center-mesh_center
        radius=float(config.workspace.radius_mm)
        offsets=[np.zeros(2),aligned]
        offsets.extend(aligned+np.array([x,y])*radius/8
            for x in range(-6,7) for y in range(-6,7))
        best=None;feasible_count=0
        weights=multiplicity/multiplicity.sum()
        def score_offset(offset):
            nonlocal best,feasible_count
            placed_hull=translate(hull,xoff=float(offset[0]),yoff=float(offset[1]))
            if not safe_workspace.covers(placed_hull) or not reach_union.covers(placed_hull): return
            shifted=xy+offset
            delta=shifted[:,None,:]-bases[None,:,:2]
            d2=np.einsum('nri,nri->nr',delta,delta)
            reachable=d2<=(radii[None,:]-INSET)**2
            if not reachable.any(axis=1).all(): return
            # Projection keeps multiplicity: every original solid sample has
            # weight one, including samples at different heights with equal XY.
            owners=np.argmin(np.where(reachable,d2,np.inf),axis=1)
            counts=np.bincount(owners,weights=multiplicity,minlength=3).round().astype(int)
            shares=counts/counts.sum()
            error=shares-1/3
            travel=float(np.sum(weights*d2[np.arange(len(xy)),owners])/scale)
            feasible_count+=1
            score=(float(np.std(shares)),float(np.max(np.abs(error))),travel,float(np.linalg.norm(offset)))
            if best is None or score<best[0]:best=(score,np.asarray(offset).copy(),counts,shares)
        for offset in offsets:score_offset(offset)
        if best is None:
            raise ValueError('No rigid XY placement fits the workspace and reach union')
        for step in (radius/32,radius/128):
            origin=best[1].copy()
            for x in (-1,0,1):
                for y in (-1,0,1):score_offset(origin+step*np.array([x,y]))
        if best is None:raise ValueError('No position fits the workspace and all three robots reach')
        _,offset,counts,shares=best
        return dict(schema=SCHEMA,point_weight=1,sample_count=int(len(points)),
            original_bounds_xyz_mm=mesh.bounds.tolist(),
            placed_bounds_xyz_mm=(mesh.bounds+np.array([offset[0],offset[1],0.])).tolist(),
            grid_spacing_mm=spacing,translation_xyz_mm=[float(offset[0]),float(offset[1]),0.],
            initial_owner='nearest_reachable_robot',projection_plane='XY',
            projected_unique_points=int(len(xy)),projection_preserves_z_multiplicity=True,
            robot_point_counts=counts.tolist(),
            robot_point_shares=shares.tolist(),feasible_candidate_count=feasible_count,
            workspace_fits=True,all_points_reachable=True,
            objective='Minimize equal-point share imbalance in XY projection using nearest reachable ownership; travel breaks ties.',
            note='One translation for every layer. Layer priority affects handoffs, not initial nearest ownership. Grid search is approximate.')

    def export(self,directory):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        (directory/'position_plan.json').write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        self.mesh.export(directory/'target.stl')

