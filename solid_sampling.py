"""Regular, equal-weight 3D samples used only to select one STL translation."""
import math
import numpy as np


def solid_points(mesh, resolution=64):
    lo, hi = mesh.bounds
    span = hi-lo
    counts = np.array([resolution, resolution,
        min(resolution, max(2, math.ceil(span[2]/max(span[:2]/resolution))))])
    axes = [lo[i]+(np.arange(counts[i])+.500123)*(span[i]/counts[i]) for i in range(3)]
    xs,ys,zs=axes
    hits=[[] for _ in range(len(xs)*len(ys))]
    for triangle in mesh.triangles:
        a,b,c=triangle
        denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denom)<1e-12: continue
        lower,upper=triangle.min(axis=0),triangle.max(axis=0)
        ix0,ix1=np.searchsorted(xs,[lower[0]-1e-9,upper[0]+1e-9])
        iy0,iy1=np.searchsorted(ys,[lower[1]-1e-9,upper[1]+1e-9])
        if ix0==ix1 or iy0==iy1: continue
        ix,iy=np.meshgrid(np.arange(ix0,ix1),np.arange(iy0,iy1))
        x,y=xs[ix.ravel()],ys[iy.ravel()]
        u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denom
        v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denom
        mask=(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)
        z=u*a[2]+v*b[2]+(1-u-v)*c[2]
        ids=iy.ravel()*len(xs)+ix.ravel()
        for index,height in zip(ids[mask],z[mask]): hits[int(index)].append(float(height))
    points=[]
    for index,heights in enumerate(hits):
        if not heights: continue
        unique=np.asarray(sorted(heights));unique=unique[np.r_[True,np.diff(unique)>1e-6]]
        if len(unique)%2: raise ValueError(f'Odd ray intersections at solid sample {index}')
        inside=np.zeros(len(zs),bool)
        for low,high in unique.reshape(-1,2): inside|=(zs>low)&(zs<high)
        points.extend((xs[index%len(xs)],ys[index//len(xs)],z) for z in zs[inside])
    if not points: raise ValueError('No interior samples for STL placement')
    return np.asarray(points), (span/counts).tolist()
