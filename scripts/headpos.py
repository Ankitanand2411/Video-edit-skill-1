#!/usr/bin/env python3
"""Head top / head x-span / body box per segment, from the cutout model's masks of the a-roll itself.

Usage:  PY headpos.py <project_dir>      (PY = the skill's Python)
Also writes <project>/headpos.json {segment id: [head top at 20%, 50%, 80% of the shot]}.
Use it to place behind-head words (baseline ~30% of the x-height below the head top, see references/layout.md),
orbit rings, and cards that must not cover the face. Coordinates are in the 1080x1920 frame.
Also prints CLOSE TO THE LENS for a shot that opens (or ends) with the speaker leaning into the phone, the moment
they press record (or reach to stop it): fix its in / out point before the build.
Runs right after assemble.py: it needs no cutout, only 5 frames a shot through the model (matte.py: the GPU when GPU
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


def edge_frames(segs):
    """{segment id: [its 3rd frame, its 3rd-last frame]}: where a shot can open on the speaker still settling after
    pressing record, or end as they reach for the phone"""
    return {s['id']: [s['frame'] + min(2, s['frames'] - 1), s['frame'] + max(0, s['frames'] - 3)] for s in segs}


CLOSE = 1.3    # head this much wider than its clip's usual (zoom taken out): the speaker leans into the lens


def head_span(alpha):
    """the head's widest span in the 10% of the frame height below its top (frame pixels), 0 when nobody is there"""
    import numpy as np
    m = alpha[::GRID, ::GRID] > 128
    rows = np.nonzero(m.any(axis=1))[0]
    if not len(rows):
        return 0
    band = m[rows[0]:rows[0] + max(1, int(.1 * m.shape[0]))]
    spans = [int(np.nonzero(r)[0][-1] - np.nonzero(r)[0][0]) for r in band if r.any()]
    return max(spans) * GRID if spans else 0


def leaning(widths, zoom, clip_median):
    """sample head widths of one shot -> the samples where the speaker is far closer to the lens than usual"""
    return [k for k, w in enumerate(widths) if w and clip_median and w / zoom >= CLOSE * clip_median]


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
    picks, edges = sample_frames(segs), edge_frames(segs)
    masks, dev = matte.masks_at(aroll, [i for v in list(picks.values()) + list(edges.values()) for i in v],
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
    # a shot that opens with the speaker still close to the lens after pressing record (or ends as they reach for it):
    # a delivered reel kept 1.5 s of the host leaning back from the phone, and cut into another take on a blurred lean
    width = {}
    for s in segs:
        for i in picks[s['id']] + edges[s['id']]:
            width[i] = head_span(masks[i])
    flagged = 0
    for clip in dict.fromkeys(s['clip'] for s in segs):
        mine = [s for s in segs if s['clip'] == clip]
        usual = sorted(width[i] / s.get('zoom', 1) for s in mine for i in picks[s['id']] if width[i])
        med = usual[len(usual) // 2] if usual else 0
        for s in mine:
            fr = [edges[s['id']][0]] + picks[s['id']] + [edges[s['id']][1]]
            close = leaning([width[i] for i in fr], s.get('zoom', 1), med)
            if close and not s.get('lean_ok'):
                flagged += 1
                where = ('opens' if 0 in close else '') + (' and ' if 0 in close and 4 in close else '') + ('ends' if 4 in close else '')
                where = where or 'is'
                print(f"NOTE CLOSE TO THE LENS {s['id']}: the shot {where} with the speaker's head "
                      f"{max(width[fr[k]] / s.get('zoom', 1) for k in close) / med:.1f}x its usual size (leaning in to start or "
                      f"stop the recording?): LOOK at its {'first' if 0 in close else 'last'} frames; move its "
                      f"{'in' if 0 in close else 'out'}-point past the lean in edl.json, drop the shot, or add \"lean_ok\": true")
    if flagged:
        print(f'{flagged} shot(s) to look at before the build')


if __name__ == '__main__':
    main()
