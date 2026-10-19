"""Scientific STL / trajectory previews from saved geometry; no evaluation."""
import csv,json
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]/'report_final'
records=json.loads((ROOT/'report_data.json').read_text(encoding='utf-8'))
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',26)
def project(a):return np.column_stack((.866*(a[:,0]-a[:,1]),.5*(a[:,0]+a[:,1])-a[:,2]))
for record in records:
    p=ROOT/record['artifact_dir'];mesh=trimesh.load(p/'input/target.stl',force='mesh',process=False)
    coords=project(np.asarray(mesh.vertices));lo=coords.min(axis=0);span=np.maximum(coords.max(axis=0)-lo,1e-6);scale=min(850/span[0],680/span[1])
    xy=(coords-lo)*scale+[70,90]
    im=Image.new('RGB',(1000,850),'white');d=ImageDraw.Draw(im)
    faces=np.asarray(mesh.faces);depth=np.asarray(mesh.vertices)[faces].mean(axis=1)@np.array([1,1,1])
    for face in faces[np.argsort(depth)]:d.polygon([tuple(xy[i]) for i in face],fill='#b2cfdf',outline='#799bac')
    d.text((20,15),record['version']+' | '+record['job']+' | input STL',font=font,fill='black');im.save(p/'target.png')
    im=Image.new('RGB',(1000,850),'white');d=ImageDraw.Draw(im);d.text((20,15),'Deposition trajectory | R1 red, R2 green, R3 blue',font=font,fill='black')
    last={};colors=['#c23b36','#238443','#3568c0']
    with (p/'input/trajectory.csv').open(encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        for r in reader:
            robot=int(r['robot_id']);point=np.array([float(r[k]) for k in ['x_mm','y_mm','z_mm']])
            if robot in last:
                a,mode=last[robot]
                if mode=='D':
                    pair=(project(np.vstack((a,point)))-lo)*scale+[70,90]
                    d.line([tuple(pair[0]),tuple(pair[1])],fill=colors[robot-1],width=1)
            last[robot]=(point,r['mode'])
    im.save(p/'trajectory.png')
print('Rendered previews for',len(records),'saved cases',flush=True)
