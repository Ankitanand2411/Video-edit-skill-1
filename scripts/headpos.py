#!/usr/bin/env python3
"""Head top / head x-span / body box per segment, from the cutout model's masks of the a-roll itself.

Usage:  PY headpos.py <project_dir>      (PY = the skill's Python)
Also writes <project>/headpos.json {segment id: [head top at 20%, 50%, 80% of the shot]}.
Use it to place behind-head words (baseline ~30% of the x-height below the head top, see references/layout.md),
orbit rings, and cards that must not cover the face. Coordinates are in the 1080x1920 frame.
Runs right after assemble.py: it needs no cutout, only 3 frames a shot through the model (matte.py: the GPU when GPU
support is installed, else the CPU; ~5 s / ~40 s for 20 shots). The masks are kept in work/masks/ for cutout.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

SAMPLES = (.2, .5, .8)
GRID = 4   # measured on a 270x480 copy of the mask, as before (values x4 = 1080x1920 pixels)


def sample_frames(segs, at=SAMPLES):
    """{segment id: [a-roll frame at 20%, 50%, 80% of the shot]}"""
    return {s['id']: [min(s['frame'] + s['frames'] - 1, s['frame'] + int(s['frames'] * f)) for f in at] for s in segs}


def measure(alpha):
    """1080x1920 uint8 alpha -> (head top, head x from, head x to, body box) in frame pixels, or None (nobody there)"""
    import numpy as np
    from PIL import Image
    w, h = alpha.shape[1] // GRID, alpha.shape[0] // GRID
    m = np.asarray(Image.fromarray(alpha, 'L').resize((w, h), Image.BICUBIC)) > 128
    rows = np.nonzero(m[:, ::2].any(axis=1))[0]
    if not len(rows):
        return None
    top = int(rows[0])
    xs = np.nonzero(m[min(h - 1, top + 25)])[0]
    cols = np.nonzero(m.any(axis=0))[0]
    body = [int(cols[0]) * GRID, top * GRID, (int(cols[-1]) + 1) * GRID, (int(rows[-1]) + 1) * GRID]
    return top * GRID, int(xs[0]) * GRID if len(xs) else 0, int(xs[-1]) * GRID if len(xs) else 0, body


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    import cutout
    import matte
    with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
        segs = json.load(fh)
    aroll = os.path.join(proj, 'assets', 'aroll.mp4')
    if not (matte.ort_ready() and os.path.isfile(matte.MODEL)):
        sys.exit('headpos: onnxruntime or the cutout model is missing: run setup.py (it installs and fetches them)')
    picks = sample_frames(segs)
    masks, dev = matte.masks_at(aroll, [i for v in picks.values() for i in v],
                                cache=os.path.join(proj, 'work', 'masks', cutout.aroll_key(aroll)))
    result = {}   # segment id -> head top at 20% / 50% / 80% of the shot
    for s in segs:
        rows, tops = [], []
        for i in picks[s['id']]:
            r = measure(masks[i])
            if not r:
                rows.append('no subject')
                continue
            rows.append(f'head top {r[0]:4d}  head x {r[1]}-{r[2]}  body {r[3]}')
            tops.append(r[0])
        result[s['id']] = tops if len(tops) == 3 else None
        print(f"{s['id']:8s} {s['frame'] / 30:6.2f}s  " + ' | '.join(rows))
    with open(os.path.join(proj, 'headpos.json'), 'w', encoding='utf-8') as fh:   # build.py reads this
        json.dump(result, fh, indent=1)
    print(f'headpos.json: {len(segs)} shots, masks on {dev}')


if __name__ == '__main__':
    main()
