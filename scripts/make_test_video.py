"""Rendert ein synthetisches Testvideo (Zeitlupe: 240 Bilder/s echt, als 30 Bilder/s gespeichert)
für den End-to-End-Test des Video-Trackers. Aufruf: python scripts/make_test_video.py /tmp/sprung.mp4
Benötigt ffmpeg und Pillow. Keine Messung – synthetische Daten aus core/synthetic.py."""
import sys, json, subprocess, numpy as np
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = sys.argv[1] if len(sys.argv) > 1 else 'sprung_zeitlupe.mp4'
from PIL import Image, ImageDraw
from core.synthetic import make_synthetic
from core.models import level2_generated as G

RATE = 240
W, H, PPM = 1280, 720, 250.0
OX, OZ = 760, 560  # Brettspitze in Ruhe [px]
trc, truth = make_synthetic(rate=RATE, noise_m=0.0)
# Punkte aus der TRC (mm) lesen
lines = trc.splitlines()
names = [n for n in lines[3].split('\t')[2:] if n]
rows = np.array([[float(x) for x in ln.split('\t')] for ln in lines[5:]])
def px(xm, zm): return (OX + xm * PPM, OZ - zm * PPM)
idx = {n: i for i, n in enumerate(names)}
pmap = {'toe': 'r_toe_study', 'ball': 'r_5meta_study', 'heel': 'r_calc_study', 'ankle': 'r_ankle_study', 'knee': 'r_knee_study',
        'hip': 'RHip', 'shoulder': 'r_shoulder_study', 'vertex': 'Head', 'elbow': 'r_lelbow_study', 'wrist': 'r_lwrist_study', 'board_tip': 'board_tip'}
gt = {k: [] for k in pmap}
ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', '30', '-i', '-',
                       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '14', '-g', '30', OUT], stdin=subprocess.PIPE)
rng = np.random.default_rng(1)
bg = (rng.normal(0, 6, (H, W, 3)) + np.array([18, 22, 30])).clip(0, 255).astype(np.uint8)
for r in rows:
    get = lambda n: (r[2 + 3 * idx[n]] / 1000, r[3 + 3 * idx[n]] / 1000)
    im = Image.fromarray(bg.copy()); d = ImageDraw.Draw(im)
    # Wasser, Brett (Fulkrum bei −3 m), Maßstab 1 m
    d.rectangle([0, 700, W, H], fill=(20, 45, 70))
    bx, bz = get('board_tip')
    d.line([px(-3.0, 0), px(bx, bz)], fill=(200, 200, 205), width=10)
    d.line([(200, 680), (450, 680)], fill=(245, 158, 11), width=4)
    for x in (200, 450): d.ellipse([x - 5, 675, x + 5, 685], fill=(245, 158, 11))
    P = {k: px(*get(v)) for k, v in pmap.items()}
    for a, b in [('toe', 'ball'), ('ball', 'heel'), ('heel', 'ankle'), ('ankle', 'knee'), ('knee', 'hip'), ('hip', 'shoulder'), ('shoulder', 'vertex'), ('shoulder', 'elbow'), ('elbow', 'wrist')]:
        d.line([P[a], P[b]], fill=(110, 110, 120), width=14)
    for k, (u, v) in P.items():
        rad = 6
        d.ellipse([u - rad - 2, v - rad - 2, u + rad + 2, v + rad + 2], fill=(0, 0, 0))
        d.ellipse([u - rad, v - rad, u + rad, v + rad], fill=(255, 220, 0) if k == 'board_tip' else (250, 250, 250))
        gt[k].append([u, v])
    ff.stdin.write(im.tobytes())
ff.stdin.close(); ff.wait()
json.dump({'gt_px': gt, 'n': len(rows), 'origin': [OX, OZ], 'scale': [[200, 680], [450, 680]], 'truth_metrics': truth['metrics'],
           't_td_file': truth['t_td_file'], 't_to_file': truth['t_to_file']}, open(OUT + '.truth.json', 'w'))
print('frames', len(rows))
