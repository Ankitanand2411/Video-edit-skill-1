#!/usr/bin/env python3
"""Words behind the head that lose letters for a few frames: find them in the rendered frames.

Usage:  PY wordcheck.py <project_dir> <render.mp4 | frames folder>     (render.py runs it on its PNG frames before the
                                                                      encode, check_cuts.py on the final render)

A reel delivered with "ans  r?", "cam   ge" and a half-faded "parents": for the first 4-17 frames a word behind the
head lost a band of letters (sharp-edged, wall showing through), then came back whole and stayed. The cutout layer was
drawn without its alpha until its next keyframe. Whatever the cause, the frames show it: while a word rests (its
entrance done, its exit not started) the number of its own-colour pixels only drifts as the head moves (the hair hides
at most the bottom of the letters), while a glitch jumps between two frames and holds. build.py writes each
behind-head word's box, colour and resting window into work/reel.json ("behind").

Returns glitch runs [(word, first frame, last frame)]; render.py throws those frames away (from the start of their
cutout piece, a keyframe) and draws them again before encoding.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

TOL = 30          # a pixel of the word's colour: every channel within this of it
DROP = .14        # a resting word showing 14% fewer of its pixels than its own best frames...
JUMP = .07        # ...with a jump of 7% or more between two frames at the edge of that run: a glitch


def glitch_runs(counts, drop=DROP, jump=JUMP):
    """[(first, last)] index runs where a resting word is missing pixels: below (1 - drop) of its best frames (90th
    percentile) and entered or left by an abrupt jump. A slow drift (the head rising into the letters) is not one."""
    if len(counts) < 4:
        return []
    ref = sorted(counts)[int(.9 * (len(counts) - 1))]
    if ref <= 0:
        return []
    low = [c < (1 - drop) * ref for c in counts]
    runs, k = [], 0
    while k < len(counts):
        if not low[k]:
            k += 1
            continue
        a = k
        while k < len(counts) and low[k]:
            k += 1
        b = k - 1
        # the jumps between two frames around the run's ends (a glitch can fade over a frame or two: "cambridge" came
        # back over 11.7k -> 13.4k -> 15.2k pixels, the run's edge sitting on the middle frame)
        near = [i for i in range(max(1, a - 2), min(len(counts), a + 3))] + [i for i in range(max(1, b - 1), min(len(counts), b + 4))]
        edges = [abs(counts[i] - counts[i - 1]) for i in set(near)]
        if any(e >= jump * ref for e in edges):
            runs.append((a, b))
    return runs


def colour(hexc):
    h = hexc.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def counts_of(src, w, fps, first, n, box, rgb, frames_dir=False):
    """own-colour pixel count of the box in n frames from `first` (a PNG folder 00000.png... or a video)"""
    import numpy as np
    x0, y0, x1, y1 = box
    if frames_dir:
        inp = ['-framerate', str(fps), '-start_number', str(first), '-i', os.path.join(src, '%05d.png')]
    else:
        inp = ['-ss', f'{first / fps:.4f}', '-i', src]
    raw = subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', *inp, '-frames:v', str(n),
                          '-vf', f'scale={w}:-2,crop={x1 - x0}:{y1 - y0}:{x0}:{y0}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, y1 - y0, x1 - x0, 3).astype(np.int16)
    near = (np.abs(fr - np.array(rgb, np.int16)).max(axis=3) <= TOL)
    return [int(c) for c in near.sum(axis=(1, 2))]


def scan(proj, src):
    """-> [(text, first frame, last frame)] glitches in a render (video) or its frames folder"""
    with open(os.path.join(proj, 'work', 'reel.json'), encoding='utf-8') as fh:
        reel = json.load(fh)
    fps, out = 30, []
    frames_dir = os.path.isdir(src)
    if frames_dir:
        width = 1080
    else:
        width = int(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width',
                                    '-of', 'csv=p=0', src], **skillenv.TEXT).stdout.strip() or 1080)
    s = width / 1080
    for wd in reel.get('behind', []):
        a, b = round(wd['rest'][0] * fps), round(wd['rest'][1] * fps)
        if b - a < 4:
            continue
        box = [max(0, int(wd['box'][0] * s)) // 2 * 2, max(0, int(wd['box'][1] * s)) // 2 * 2,
               min(width, int(wd['box'][2] * s)) // 2 * 2, min(int(1920 * s), int(wd['box'][3] * s)) // 2 * 2]
        if frames_dir and not all(os.path.exists(os.path.join(src, f'{n:05d}.png')) for n in (a, b - 1)):
            continue
        c = counts_of(src, width, fps, a, b - a, box, colour(wd['colour']), frames_dir)
        out += [(wd['text'], a + x, a + y) for x, y in glitch_runs(c)]
    return out


def main():
    skillenv.utf8_stdio()
    proj, src = skillenv.path_arg(sys.argv[1]), skillenv.path_arg(sys.argv[2])
    bad = scan(proj, src)
    for text, x, y in bad:
        print(f'WORD GLITCH {text!r}: frames {x}-{y} ({x / 30:.2f}-{(y + 1) / 30:.2f}s) lose part of the word')
    print('WORDS OK: every word behind the head stays whole' if not bad else f'{len(bad)} word glitch(es)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
