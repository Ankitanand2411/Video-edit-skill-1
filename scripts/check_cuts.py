#!/usr/bin/env python3
"""Frame-exact QA of a render: the last frame before and first frame after every cut, in one strip, plus a phone copy.

Usage:  PY check_cuts.py <project_dir> <render.mp4> [--phone]
Writes work/cut_check.jpg (pairs left->right: before|after for each cut). LOOK at it: every 'after' frame must show the
new shot with that section's look and no leftovers (room plates, cutout of the previous shot, stale captions).
Snapshots from `hyperframes snapshot` seek approximately at cuts; only frames pulled from the final render are proof.
--phone also writes <render>-phone.mp4 (720p, crf 26, the render's own audio copied; SendUserFile uploads over ~5MB
often fail, drop to crf 28).
It also checks lip sync: each shot's sound in the render is located in the original clip and compared with the
picture's source time (sources.json + segments.json); every shot should read 0 ms (a few ms is fine).
"""
import json
import os
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

skillenv.utf8_stdio()
FF = skillenv.tool('ffmpeg')
proj, render = skillenv.path_arg(sys.argv[1]), skillenv.path_arg(sys.argv[2])
with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
    segs = json.load(fh)
cf = os.path.join(proj, 'work', 'cf')
sheet = os.path.join(proj, 'work', 'cut_check.jpg')
os.makedirs(cf, exist_ok=True)
phone = []
if '--phone' in sys.argv:   # encodes while the cut sheet and the lip sync check run
    out = os.path.splitext(render)[0] + '-phone.mp4'

    def phone_copy():
        subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', 'scale=720:-2', '-c:v', 'libx264', '-crf', '26', '-preset', 'slow',
                        '-c:a', 'copy', '-movflags', '+faststart', out], check=True)   # audio copied: a 2nd AAC pass audibly degrades it
        phone.append(f'phone copy {out} {os.path.getsize(out) / 1e6:.1f} MB')
    th = threading.Thread(target=phone_copy)
    th.start()
# every frame the sheet needs, in one decode (one ffmpeg per frame decoded the render up to that frame 38 times)
want = sorted({n for s in segs[1:] for n in (s['frame'] - 1, s['frame'])})
for f in os.listdir(cf):
    if f.startswith('q') and f.endswith('.png'):
        os.remove(os.path.join(cf, f))   # this script's own frames from an earlier run
sel = '+'.join(f'eq(n,{n})' for n in want)
subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', f"select='{sel}',scale=150:-2", '-fps_mode', 'passthrough',
                os.path.join(cf, 'q%04d.png')], check=True)
got = {n: os.path.join(cf, f'q{k + 1:04d}.png') for k, n in enumerate(want)}
pngs = [got[n] for s in segs[1:] for n in (s['frame'] - 1, s['frame'])]
ins = sum((['-i', p] for p in pngs), [])
subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', f'hstack={len(pngs)}', sheet], check=True)
print('cuts at frames', [s['frame'] for s in segs[1:]], '->', sheet)


def sync_check():
    """sound vs picture per shot, against the original clips: + = the sound runs ahead of the picture"""
    import numpy as np
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        sources = json.load(fh)

    def pcm(f, ss, t):
        raw = subprocess.run([FF, '-v', 'error', '-ss', f'{max(0, ss):.3f}', '-t', f'{t:.3f}', '-i', f, '-vn', '-ac', '1', '-ar', '8000',
                              '-af', 'highpass=f=100', '-f', 'f32le', '-'], capture_output=True).stdout
        return np.frombuffer(raw, np.float32).astype(np.float64)
    # the render's audio decoded straight through (no seeking): a soundtrack whose gaps live only in timestamps is
    # caught here, the way a straight-through decoder (an editor, a transcoder) would play it
    raw = subprocess.run([FF, '-v', 'error', '-i', render, '-vn', '-ac', '1', '-ar', '8000', '-af', 'highpass=f=100', '-f', 'f32le', '-'],
                         capture_output=True).stdout
    whole = np.frombuffer(raw, np.float32).astype(np.float64)
    off = []
    for s in segs:
        if s['frames'] < 24:
            off.append(None); continue
        t = s['frame'] / 30 + min(0.5, s['frames'] / 60)
        src_t = s['src_in'] + (t - s['frame'] / 30)
        x, ref = whole[int(t * 8000):int((t + 0.8) * 8000)], pcm(sources[s['clip']], src_t - 1.0, 2.8)
        if len(x) < 100 or len(ref) <= len(x) or not x.any():
            off.append(None); continue
        c = np.correlate(ref, x, mode='valid')
        n = np.sqrt(np.convolve(ref ** 2, np.ones(len(x)), mode='valid')) * np.linalg.norm(x) + 1e-9
        start = max(0, src_t - 1.0)
        off.append(round((start + int(np.argmax(c / n)) / 8000 - src_t) * 1000))
    print('lip sync per shot, ms (+ = sound early):', off)
    bad = [s['id'] for s, o in zip(segs, off) if o is not None and abs(o) > 45]
    print('LIP SYNC OK' if not bad else f'LIP SYNC OFF in {bad}: the soundtrack drifted (see gotchas.md, audio)')


if '--no-sync' not in sys.argv:
    sync_check()
if '--phone' in sys.argv:
    th.join()
    if not phone:
        sys.exit('phone copy failed (see above)')
    print(phone[0])
