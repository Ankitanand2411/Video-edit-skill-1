#!/usr/bin/env python3
"""Cut the speaker out of the assembled cut -> <project>/assets/subject.webm (VP9 + alpha), then verify it is
frame-for-frame the same length as aroll.mp4 (a mismatch means the cutout will drift; re-run assemble.py).

Usage:  PY cutout.py <project_dir> [--engine hyperframes] [extra remove-background arguments, e.g. --device cpu]
With GPU support installed (setup.py --gpu: an NVIDIA GPU on Linux / Windows, or DirectML on Windows) the skill's own
engine does it (matte.py: HyperFrames' recipe and model, on the GPU, CPU fallback frame by frame): GTX 1650, 1936
frames in ~6 min (5.5 frames/s) instead of ~32. Otherwise HyperFrames: ~7s per second of footage on Apple Silicon
(CoreML); on a CPU ~1 frame/s, depending on the processor. `--engine hyperframes` forces HyperFrames.
Run it in the background, one cutout at a time (~1.5 GB of RAM). The first run downloads the model (~170 MB).
Prints a progress line every 30s.
"""
import collections
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def frames(f):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                          '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', f], **skillenv.TEXT).stdout
    return out.strip().split(',')[0]


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


def gpu_engine_ready():
    """the skill's own cutout engine runs when onnxruntime here has a CUDA or DirectML provider (setup.py --gpu).
    Macs keep HyperFrames' CoreML path, which already uses the Apple GPU; everything else keeps HyperFrames on the CPU."""
    try:
        import matte
        if not (matte.ort_ready() and os.path.isfile(matte.MODEL)):
            return False
        import onnxruntime
        return bool({'CUDAExecutionProvider', 'DmlExecutionProvider'} & set(onnxruntime.get_available_providers()))
    except Exception:
        return False


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    aroll, subject = os.path.join(proj, 'assets', 'aroll.mp4'), os.path.join(proj, 'assets', 'subject.webm')
    if not os.path.isfile(aroll):
        sys.exit(f'{aroll} not found: run assemble.py first.')
    engine = sys.argv[sys.argv.index('--engine') + 1] if '--engine' in sys.argv else 'auto'
    extra = [x for i, x in enumerate(sys.argv[2:], 2) if x != '--engine' and sys.argv[i - 1] != '--engine']
    if engine != 'hyperframes' and gpu_engine_ready():
        # the skill's own engine (matte.py): HyperFrames' recipe on CUDA / DirectML, CPU fallback frame by frame
        import matte
        t0 = time.time()
        res = matte.matte(aroll, subject)
        a, s = frames(aroll), frames(subject)
        print(f'aroll frames {a} / cutout frames {s}   ({time.time() - t0:.0f}s, {res["device"]})')
        if not a or a != s:
            sys.exit('FRAME MISMATCH: cutout will drift. Re-run assemble.py (clean CFR) then this script.')
        return
    # relative paths + cwd: nothing with the user's folder name goes through npx's argument handling
    argv, env = skillenv.hyperframes_command(['remove-background', 'assets/aroll.mp4', '-o', 'assets/subject.webm',
                                              '--quality', 'best'] + extra)
    t0 = time.time()
    code, last = run(argv, env, proj)
    if code != 0:
        print('\n'.join(last))
        sys.exit(f'remove-background failed (exit {code}). Lines above are the end of its output.')
    if last:
        print(last[-1])
    a, s = frames(aroll), frames(subject)
    print(f'aroll frames {a} / cutout frames {s}   ({time.time() - t0:.0f}s)')
    if not a or a != s:
        sys.exit('FRAME MISMATCH: cutout will drift. Re-run assemble.py (clean CFR) then this script.')


if __name__ == '__main__':
    main()
