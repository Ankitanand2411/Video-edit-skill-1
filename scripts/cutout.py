#!/usr/bin/env python3
"""Cut the speaker out of the a-roll where the reel needs it -> <project>/assets/subject/<first>-<end>.webm
(VP9 + alpha), one file per piece of work/cutout_plan.json, which build.py writes: only the frames where something
sits behind the head (every frame when the look grades the cutout on its own). Each piece is checked frame for frame
against its length in the plan (a mismatch means the cutout would drift).

Usage:  PY cutout.py <project_dir> [--engine ours|hyperframes] [--device cuda|dml|cpu] [--workers N]
Run it after every build that moves behind-head words (build.py's last line says when pieces are missing): pieces
already cut out are kept, and masks are kept per frame (work/masks/), so a rebuild only runs the model on new frames.
A project without work/cutout_plan.json (an older build.py) gets the old single file, assets/subject.webm, every frame.

Engines:
  ours (matte.py)      HyperFrames' recipe and model in Python: the GPU when GPU support is installed (CUDA, DirectML),
                       every CPU core otherwise; several pieces side by side. GTX 1650 laptop: ~7 frames/s on the GPU,
                       ~1.6 on its 6-core CPU. The default everywhere except Apple Silicon.
  hyperframes          HyperFrames' own remove-background, one piece at a time (the Apple GPU through CoreML on a Mac:
                       ~7 s per second of footage). The default on Apple Silicon; `--engine hyperframes` elsewhere.
The first run downloads the model (~170 MB) if setup.py has not. Prints a progress line every 30 s.
"""
import collections
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
PIECE = re.compile(r'^\d{5}-\d{5}\.webm$')


def split_progress(buf):
    """-> (finished lines, unfinished rest). HyperFrames redraws its spinner with cursor escape codes instead of
    newlines, so every escape code counts as a line break, and the spinner glyph in front is dropped."""
    *lines, rest = re.split(r'[\r\n]+', ANSI.sub('\n', buf))
    return [l for l in (re.sub(r'^[^\w\[(]+', '', l).strip() for l in lines) if l], rest


def run(argv, env, cwd, every=30):
    """Run quietly like `| tail -1`, but print the newest progress line every `every` seconds so a long CPU run in
    the background is visibly alive. Returns (exit code, last lines)."""
    last, shown, t_print = collections.deque(maxlen=25), '', time.time()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = ''
    while True:
        chunk = proc.stdout.read1(4096)
        if not chunk:
            break
        lines, buf = split_progress(buf + chunk.decode('utf-8', 'replace'))
        for l in lines:
            if not last or l != last[-1]:
                last.append(l)
        if last and last[-1] != shown and time.time() - t_print >= every:
            shown, t_print = last[-1], time.time()
            print(shown, flush=True)
    for l in split_progress(buf + '\n')[0]:
        last.append(l)
    return proc.wait(), list(last)


def aroll_key(path):
    """the a-roll's identity: a re-assembled a-roll gets new pieces and new masks"""
    st = os.stat(path)
    return f'{st.st_size}-{int(st.st_mtime)}'


def todo(pieces, done, key, exists, frames_of):
    """pieces still to cut out: missing, made from another a-roll, or not the length the plan says"""
    out = []
    for p in pieces:
        rec = done.get(p['file'])
        if not (exists(p['file']) and rec and rec.get('aroll') == key and rec.get('frames') == p['b'] - p['a']
                and frames_of(p['file']) == p['b'] - p['a']):
            out.append(p)
    return out


def choose_engine(argv, osn, arch):
    if '--engine' in argv:
        return argv[argv.index('--engine') + 1]
    return 'hyperframes' if osn == 'macos' and arch == 'arm64' else 'ours'


def hyperframes_piece(proj, aroll, a, b, out):
    """frames [a, b) -> a lossless clip -> HyperFrames remove-background -> out"""
    import matte
    ff = skillenv.tool('ffmpeg')
    tmp_in = os.path.join(proj, 'work', 'cut_in', f'{a:05d}-{b:05d}.mp4')
    os.makedirs(os.path.dirname(tmp_in), exist_ok=True)
    dec = matte.decoder_args(ff, aroll, a, b - a)
    seek = dec[dec.index('-ss'):dec.index('-ss') + 2] if '-ss' in dec else []
    subprocess.run([ff, '-loglevel', 'error', '-y'] + seek + ['-i', aroll, '-frames:v', str(b - a), '-an', '-c:v', 'libx264',
                    '-qp', '0', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', tmp_in], check=True)
    part = out + '.part.webm'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    argv, env = skillenv.hyperframes_command(['remove-background', os.path.relpath(tmp_in, proj), '-o', os.path.relpath(part, proj),
                                              '--quality', 'best'])
    code, last = run(argv, env, proj)
    os.remove(tmp_in)   # our own intermediate
    if code != 0:
        print('\n'.join(last))
        sys.exit(f'remove-background failed on frames {a}-{b} (exit {code}). Lines above are the end of its output.')
    os.replace(part, out)


def device_arg(argv):
    return argv[argv.index('--device') + 1] if '--device' in argv else 'auto'


def legacy(proj, aroll, engine, extra):
    """no cutout plan (a build.py from before the plan): every frame into assets/subject.webm, as before"""
    import matte
    subject = os.path.join(proj, 'assets', 'subject.webm')
    t0 = time.time()
    if engine == 'ours':
        dev = matte.matte(aroll, subject, device_arg(extra))['device']
    else:
        argv, env = skillenv.hyperframes_command(['remove-background', 'assets/aroll.mp4', '-o', 'assets/subject.webm',
                                                  '--quality', 'best'] + extra)
        code, last = run(argv, env, proj)
        if code != 0:
            print('\n'.join(last))
            sys.exit(f'remove-background failed (exit {code}). Lines above are the end of its output.')
        dev = 'hyperframes'
    a, s = matte.packets(aroll), matte.packets(subject)
    print(f'aroll frames {a} / cutout frames {s}   ({time.time() - t0:.0f}s, {dev})')
    if not a or a != s:
        sys.exit('FRAME MISMATCH: cutout will drift. Re-run assemble.py (clean CFR) then this script.')


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    aroll = os.path.join(proj, 'assets', 'aroll.mp4')
    if not os.path.isfile(aroll):
        sys.exit(f'{aroll} not found: run assemble.py first.')
    import matte
    info = skillenv.detect()
    engine = choose_engine(sys.argv, info['os'], info['arch'])
    if engine == 'ours' and not (matte.ort_ready() and os.path.isfile(matte.MODEL)):
        print('cutout: onnxruntime or the model is missing here: HyperFrames does it (run setup.py to fix)')
        engine = 'hyperframes'
    flags = ('--engine', '--workers')
    extra = [x for i, x in enumerate(sys.argv[2:], 2) if x not in flags and sys.argv[i - 1] not in flags]
    plan_file = os.path.join(proj, 'work', 'cutout_plan.json')
    if not os.path.isfile(plan_file):
        return legacy(proj, aroll, engine, extra)
    with open(plan_file, encoding='utf-8') as fh:
        plan = json.load(fh)
    n_aroll = matte.packets(aroll)
    if plan['frames'] != n_aroll:
        sys.exit(f"cutout_plan.json is for {plan['frames']} frames, aroll.mp4 has {n_aroll}: run build.py again first.")
    key = aroll_key(aroll)
    done_file = os.path.join(proj, 'work', 'cutout_done.json')
    done = {}
    if os.path.isfile(done_file):
        with open(done_file, encoding='utf-8') as fh:
            done = json.load(fh)
    path = lambda f: os.path.join(proj, f)
    need = todo(plan['pieces'], done, key, lambda f: os.path.isfile(path(f)), lambda f: matte.packets(path(f)))
    keep = {os.path.basename(p['file']) for p in plan['pieces']}
    old = [f for f in glob.glob(os.path.join(proj, 'assets', 'subject', '*.webm'))
           if PIECE.match(os.path.basename(f)) and os.path.basename(f) not in keep]
    for f in old:   # this script's own pieces that the build no longer shows
        os.remove(f)
    frames = sum(p['b'] - p['a'] for p in plan['pieces'])
    print(f"cutout plan: {frames} of {plan['frames']} frames in {len(plan['pieces'])} pieces"
          f"{' (every frame: the look grades the cutout on its own)' if plan.get('every_frame') else ' (where something is behind the head)'};"
          f" {len(need)} to cut out" + (f", {len(old)} old pieces removed" if old else ''), flush=True)
    t0, dev = time.time(), None
    if need and engine == 'ours':
        workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else None
        res = matte.cut(aroll, [(p['a'], p['b'], path(p['file'])) for p in need], device_arg(sys.argv),
                        os.path.join(proj, 'work', 'masks', key), workers)
        dev = res['device']
    elif need:
        for k, p in enumerate(need):
            print(f"   hyperframes: piece {k + 1}/{len(need)} (frames {p['a']}-{p['b']})", flush=True)
            hyperframes_piece(proj, aroll, p['a'], p['b'], path(p['file']))
        dev = 'hyperframes'
    bad = []
    for p in need:
        n = matte.packets(path(p['file']))
        if n == p['b'] - p['a']:
            done[p['file']] = {'aroll': key, 'frames': n}
        else:
            bad.append(f"{p['file']} has {n} frames, needs {p['b'] - p['a']}")
    with open(done_file, 'w', encoding='utf-8') as fh:
        json.dump({p['file']: done[p['file']] for p in plan['pieces'] if p['file'] in done}, fh, indent=1)
    if bad:
        sys.exit('FRAME MISMATCH: ' + '; '.join(bad) + '. Run this script again.')
    if need:
        print(f"cutout done: {len(need)} pieces, {sum(p['b'] - p['a'] for p in need)} frames in {time.time() - t0:.0f}s "
              f"({dev}); every piece frame-exact")
    else:
        print('cutout: every piece already cut out')


if __name__ == '__main__':
    main()
