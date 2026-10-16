#!/usr/bin/env python3
"""The skill's own background removal: HyperFrames' remove-background recipe (same model file, same steps, same VP9
encode) run through onnxruntime for Python, so the cutout can use the GPU on every OS:
CUDA (NVIDIA, Linux and Windows), DirectML (any DirectX 12 GPU on Windows: NVIDIA, AMD, Intel), CoreML (Mac), and
every core of the CPU otherwise (onnxruntime comes with faster-whisper, so every skill venv has it).
HyperFrames 0.8.34 itself offers CUDA on Linux only (its Windows build ships DirectML but no way to choose it) and
CoreML on Apple Silicon only.

Usage:  PY matte.py <input.mp4> <output.webm> [--device auto|cuda|dml|coreml|cpu]   (one clip, every frame)
        PY matte.py --info                                                         (what this machine can run it on)
cutout.py calls cut() with the pieces the build needs (work/cutout_plan.json); headpos.py calls masks_at().

Recipe (hyperframes@0.8.34 dist/cli.js: background-removal/inference.ts + pipeline.ts):
  ffmpeg decode rgb24 -> lanczos3 resize to 320x320 -> divide by the brightest value -> (x - mean) / std (ImageNet)
  -> u2net_human_seg -> first output plane min-max to 0..255 -> lanczos3 resize to the frame -> alpha
  -> ffmpeg VP9 crf 12 ("best"), deadline good, cpu-used 4, row-mt, yuva420p, BT.709 tags, alpha_mode=1.
Speed (GTX 1650 laptop, 6 cores): model on the GPU ~11 frames/s, on the CPU ~1.6; one VP9 alpha encoder ~7.4 frames/s,
so pieces are cut out side by side, each with its own encoder (one shared model: onnxruntime runs are thread-safe).
Masks are kept per a-roll frame (work/masks/): a rebuild that moves the pieces only runs the model on new frames.
Before the first frame, the GPU and the CPU matte it and the masks are compared (self-test): a GPU path that does not
match is not used. A GPU error on frame N re-runs frame N on the CPU and everything after stays there: nothing done
is lost. Prints the device and frames/s.
"""
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

MODEL = os.path.join(os.path.expanduser('~'), '.cache', 'hyperframes', 'background-removal', 'models', 'u2net_human_seg.onnx')
SIZE = 320
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
CRF = 12             # HyperFrames QUALITY_CRF['best'], what cutout.py asks for
SELFTEST_DB = 40.0   # GPU mask vs CPU mask on the first frame, PSNR of the alpha
PROVIDER = {'cuda': 'CUDAExecutionProvider', 'dml': 'DmlExecutionProvider', 'coreml': 'CoreMLExecutionProvider',
            'cpu': 'CPUExecutionProvider'}
JOB_MB, SESSION_MB, RESERVE_MB = 1000, 700, 1000   # RAM: one piece in flight (VP9 alpha encoder ~0.8 GB + decoder), the model


# ------------------------------------------------------------------ pure parts (unit-tested)
def gpu_order(osn, arch):
    """GPU providers worth trying on this OS, best first"""
    if osn == 'macos':
        return ['coreml']
    if osn == 'windows':
        return ['cuda', 'dml']
    return ['cuda']


def ort_package(osn, nvidia):
    """the onnxruntime build setup.py installs: one package, they conflict with each other"""
    if osn == 'macos':
        return 'onnxruntime'
    if nvidia:
        return 'onnxruntime-gpu'
    return 'onnxruntime-directml' if osn == 'windows' else 'onnxruntime'


def plan_workers(jobs, cores, avail_mb):
    """pieces cut out at the same time: each has its own VP9 alpha encoder (~6 threads, ~0.8 GB peak) and decoder; at
    least 1. GTX 1650 laptop, 8 pieces: 1 at a time 5.1 frames/s, 2 6.6, 3 7.0 (two encoders top out ~12 frames/s)"""
    if not jobs:
        return 0
    by_ram = (avail_mb - RESERVE_MB - SESSION_MB) // JOB_MB if avail_mb else 1
    return int(max(1, min(jobs, max(1, (cores or 1) // 3), by_ram)))


def preprocess(rgb):
    """HxWx3 uint8 frame -> 1x3x320x320 float32 tensor, as HyperFrames' preprocess()"""
    import numpy as np
    from PIL import Image
    small = np.asarray(Image.fromarray(rgb).resize((SIZE, SIZE), Image.LANCZOS), dtype=np.float32)
    small = small / max(float(small.max()), 1.0)
    small = (small - np.array(MEAN, np.float32)) / np.array(STD, np.float32)
    return np.ascontiguousarray(small.transpose(2, 0, 1)[None], dtype=np.float32)


def small_mask(out):
    """model output -> 320x320 uint8: min-max of the first plane, rounded (HyperFrames' postprocess before the resize;
    what the cache keeps)"""
    import numpy as np
    plane = np.asarray(out, dtype=np.float32).reshape(-1)[:SIZE * SIZE].reshape(SIZE, SIZE)
    lo, hi = float(plane.min()), float(plane.max())
    return np.clip(np.round((plane - lo) / ((hi - lo) or 1.0) * 255.0), 0, 255).astype(np.uint8)


def full_mask(small, width, height):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.fromarray(small, 'L').resize((width, height), Image.LANCZOS))


def mask_of(out, width, height):
    """model output -> HxW uint8 alpha, as HyperFrames' postprocess(): min-max of the first plane, round, resize"""
    return full_mask(small_mask(out), width, height)


def psnr(a, b):
    import numpy as np
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def encoder_args(ff, width, height, fps, out, crf=CRF):
    return [ff, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{width}x{height}', '-r', str(fps), '-i', '-',
            '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', str(crf), '-deadline', 'good', '-row-mt', '1', '-cpu-used', '4',
            '-auto-alt-ref', '0', '-pix_fmt', 'yuva420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc',
            'bt709', '-color_range', 'tv', '-metadata:s:v:0', 'alpha_mode=1', '-an', out]


def decoder_args(ff, src, first=0, count=None, fps=30):
    """raw rgb24 frames from `first` on. The seek is a quarter frame early: ffmpeg drops a frame that starts even a
    hair before -ss, so an exact time can start a frame late."""
    seek = ['-ss', f'{(first - .25) / fps:.6f}'] if first > 0 else []
    return ([ff, '-loglevel', 'error', '-threads', '2'] + seek + ['-i', src] + (['-frames:v', str(count)] if count else [])
            + ['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-an', '-'])


# ------------------------------------------------------------------ onnxruntime
def ort_ready():
    """onnxruntime importable (after loading the pip NVIDIA libraries on a CUDA machine)"""
    skillenv.load_cuda_libs()
    try:
        import onnxruntime
    except ImportError:
        return False
    if os.name == 'nt' and hasattr(onnxruntime, 'preload_dlls'):   # Windows: onnxruntime's own loader for the pip NVIDIA DLLs
        try:
            onnxruntime.preload_dlls()
        except Exception:
            pass
    return True


def session(device):
    """-> (InferenceSession, device it really runs on). onnxruntime quietly falls back to the CPU when a GPU provider
    cannot load, so the device comes from the session itself."""
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.log_severity_level = 3
    if device == 'cpu':   # one thread per physical core: 1.61 frames/s vs 1.50 with onnxruntime's default (6-core Ryzen)
        so.intra_op_num_threads = skillenv.physical_cores()
    want = [PROVIDER[device]] + (['CPUExecutionProvider'] if device != 'cpu' else [])
    s = ort.InferenceSession(MODEL, so, providers=[p for p in want if p in ort.get_available_providers()] or ['CPUExecutionProvider'])
    # onnxruntime otherwise re-creates the session on the CPU when a GPU kernel fails at run time and carries on as if
    # nothing happened (cuDNN 9.27 + onnxruntime 1.22 on a GTX 1650: a "cuda" self-test that compared the CPU with
    # itself). With the fallback off, a GPU failure raises and this script decides.
    s.disable_fallback()
    used = s.get_providers()[0]
    return s, next((k for k, v in PROVIDER.items() if v == used), 'cpu')


def run(s, tensor):
    return s.run(None, {s.get_inputs()[0].name: tensor})[0]


def pick(osn, arch, frame, say=print):
    """-> (session, device): the first GPU provider that loads and matches the CPU on `frame`, else the CPU"""
    cpu, _ = session('cpu')
    t = preprocess(frame)
    ref = mask_of(run(cpu, t), frame.shape[1], frame.shape[0])
    for dev in gpu_order(osn, arch):
        try:
            s, got = session(dev)
            if got != dev:
                say(f'matte: {dev} not available here')
                continue
            db = psnr(mask_of(run(s, t), frame.shape[1], frame.shape[0]), ref)
            if s.get_providers()[0] != PROVIDER[dev]:   # belt and braces: the run really happened on the GPU
                say(f'matte: {dev} moved itself to {s.get_providers()[0]}: not used')
                continue
            if db >= SELFTEST_DB:
                say(f'matte: {dev} self-test passed (mask {db:.1f} dB vs the CPU)')
                del cpu   # ~0.6 GB back; a GPU failure later makes a new one
                return s, dev
            say(f'matte: {dev} self-test FAILED (mask {db:.1f} dB vs the CPU, need {SELFTEST_DB:.0f}): not used')
        except Exception as e:   # driver, library, out of memory: this provider is out
            say(f'matte: {dev} failed to start ({str(e).splitlines()[0][:160]})')
    return cpu, 'cpu'


class Engine:
    """one model for every worker thread. The device is chosen on the first frame (self-test); a GPU error moves it to
    the CPU for good, and that frame is redone there."""

    def __init__(self, device='auto', say=print):
        self.want, self.say = device, say
        self.s, self.dev, self.fallback_at, self.frames = None, None, None, 0
        self.lock = threading.Lock()

    def start(self, frame):
        with self.lock:
            if self.s is None:
                if not ort_ready():
                    raise RuntimeError('onnxruntime is not installed in the skill venv: run setup.py')
                info = skillenv.detect()
                self.s, self.dev = pick(info['os'], info['arch'], frame, self.say) if self.want == 'auto' else session(self.want)
        return self.dev

    def __call__(self, frame, idx):
        """-> 320x320 uint8 mask of this frame"""
        self.start(frame)
        return self.infer(preprocess(frame), idx)

    def infer(self, x, idx):
        """preprocessed tensor -> 320x320 uint8 mask (start() ran first)"""
        s, dev = self.s, self.dev
        try:
            y = run(s, x)
        except Exception as e:   # GPU trouble mid-clip: this frame and the rest on the CPU
            if dev == 'cpu':
                raise
            with self.lock:
                if self.dev != 'cpu':
                    self.say(f"matte: {dev} failed at frame {idx} ({str(e).splitlines()[0][:120]}): continuing on the CPU")
                    self.s, self.dev, self.fallback_at = session('cpu')[0], 'cpu', idx
            y = run(self.s, x)
        self.frames += 1
        return small_mask(y)


class Masks:
    """model masks per a-roll frame (320x320 PNG, before the resize: exactly what the alpha is made from). None = no
    cache. Tied to one a-roll: cutout.py keys the folder by the a-roll's size and time."""

    def __init__(self, folder=None):
        self.dir = folder
        if folder:
            os.makedirs(folder, exist_ok=True)

    def path(self, idx):
        return os.path.join(self.dir, f'{idx:05d}.png')

    def get(self, idx):
        if not self.dir or not os.path.isfile(self.path(idx)):
            return None
        import numpy as np
        from PIL import Image
        try:
            m = np.asarray(Image.open(self.path(idx)).convert('L'))
            return m if m.shape == (SIZE, SIZE) else None
        except OSError:   # cut short (a killed run): made again
            return None

    def put(self, idx, m):
        if self.dir:
            from PIL import Image
            tmp = self.path(idx) + '.tmp.png'
            Image.fromarray(m, 'L').save(tmp, compress_level=1)
            os.replace(tmp, self.path(idx))


# ------------------------------------------------------------------ the clip
def probe(path):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout.strip().split(',')
    num, den = out[2].split('/')
    return int(out[0]), int(out[1]), round(int(num) / int(den), 3)


def compose(frame, small):
    """RGBA bytes for the encoder: the frame with the mask as alpha (HyperFrames' applyMask)"""
    import numpy as np
    h, w = frame.shape[:2]
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = frame
    rgba[..., 3] = full_mask(small, w, h)
    return rgba.tobytes()


def read_frames(proc, w, h):
    import numpy as np
    n = w * h * 3
    while True:
        buf = proc.stdout.read(n)
        if len(buf) < n:
            return
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)


def packets(path):
    """frames in a video without decoding it (one packet per frame in our webm / mp4 files): ~0.1 s, not ~20 s"""
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
                          'stream=nb_read_packets', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout.strip()
    return int(out.split(',')[0]) if out.split(',')[0].isdigit() else 0


DEPTH = 3   # frames in flight on each side of the model: resizing (CPU threads) overlaps the inference (GPU)


def cut_one(src, a, b, out, engine, masks, size, pool):
    """frames [a, b) of src -> out (VP9 + alpha). The pool resizes frame n+1 and finishes frame n-1 while the model
    runs on frame n. Written as out.part first: a killed run never leaves a short piece."""
    import collections
    w, h, fps = size
    ff = skillenv.tool('ffmpeg')
    tmp = out + '.part.webm'
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    dec = subprocess.Popen(decoder_args(ff, src, a, b - a, fps), stdout=subprocess.PIPE)
    enc = subprocess.Popen(encoder_args(ff, w, h, fps, tmp), stdin=subprocess.PIPE)
    pre, post, count = collections.deque(), collections.deque(), {'n': 0, 'new': 0}

    def step():
        idx, frame, m, fut = pre.popleft()
        if m is None:
            m = engine.infer(fut.result(), idx)
            masks.put(idx, m)
            count['new'] += 1
        post.append(pool.submit(compose, frame, m))
        while len(post) > DEPTH:
            enc.stdin.write(post.popleft().result())
        count['n'] += 1

    try:
        for k, frame in enumerate(read_frames(dec, w, h)):
            m = masks.get(a + k)
            if m is None:
                engine.start(frame)
            pre.append((a + k, frame, m, None if m is not None else pool.submit(preprocess, frame)))
            if len(pre) > DEPTH:
                step()
        while pre:
            step()
        while post:
            enc.stdin.write(post.popleft().result())
    finally:
        enc.stdin.close()
        enc.wait()
        dec.stdout.close()
        dec.wait()
    n = count['n']
    if enc.returncode or n != b - a:
        raise RuntimeError(f'piece {a}-{b}: {n} of {b - a} frames, encoder exit {enc.returncode}')
    os.replace(tmp, out)
    return {'a': a, 'b': b, 'file': out, 'model_frames': count['new']}


def cut(src, jobs, device='auto', cache=None, workers=None, say=print):
    """jobs [(a, b, out file)]: frames [a, b) of src cut out into each file, several pieces at a time.
    -> {'pieces', 'frames', 'model_frames', 'seconds', 'device', 'fallback_at', 'workers'}"""
    from concurrent.futures import ThreadPoolExecutor
    size = probe(src)
    engine, masks = Engine(device, say), Masks(cache)
    total_mb, avail_mb = skillenv.memory_mb()
    workers = workers or plan_workers(len(jobs), os.cpu_count(), avail_mb)
    t0, done, shown = time.time(), [], [time.time()]

    pool = ThreadPoolExecutor(max(2, min(8, (os.cpu_count() or 2) - 1)))

    def one(job):
        r = cut_one(src, job[0], job[1], job[2], engine, masks, size, pool)
        done.append(r)
        if time.time() - shown[0] >= 30:
            shown[0] = time.time()
            n = sum(x['b'] - x['a'] for x in done)
            say(f"matte: {len(done)}/{len(jobs)} pieces, {n} frames, {engine.frames / (shown[0] - t0):.2f} model frames/s on {engine.dev}")
        return r

    try:
        with ThreadPoolExecutor(max(1, workers)) as ex:
            res = list(ex.map(one, jobs))
    finally:
        pool.shutdown(wait=True)
    dt = time.time() - t0
    frames, model = sum(r['b'] - r['a'] for r in res), sum(r['model_frames'] for r in res)
    dev = engine.dev or 'cache'
    say(f'matte: {len(res)} pieces, {frames} frames ({model} through the model, the rest from the cache) in {dt:.0f}s '
        f'on {dev}, {workers} at a time' + (f' (GPU until frame {engine.fallback_at}, CPU after)' if engine.fallback_at is not None else ''))
    return {'pieces': res, 'frames': frames, 'model_frames': model, 'seconds': dt, 'device': dev,
            'fallback_at': engine.fallback_at, 'workers': workers}


def masks_at(src, idxs, device='auto', cache=None, say=print):
    """{frame index: full-size HxW uint8 alpha} for a few frames of src (headpos.py), one decode pass"""
    w, h, fps = probe(src)
    engine, masks = Engine(device, say), Masks(cache)
    want = sorted(set(idxs))
    out, todo = {}, []
    for i in want:
        m = masks.get(i)
        if m is None:
            todo.append(i)
        else:
            out[i] = m
    if todo:
        sel = '+'.join(f'eq(n,{i})' for i in todo)
        ff = skillenv.tool('ffmpeg')
        dec = subprocess.Popen([ff, '-loglevel', 'error', '-i', src, '-vf', f"select='{sel}'", '-fps_mode', 'passthrough',
                                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-an', '-'], stdout=subprocess.PIPE)
        try:
            for i, frame in zip(todo, read_frames(dec, w, h)):
                out[i] = engine(frame, i)
                masks.put(i, out[i])
        finally:
            dec.stdout.close()
            dec.wait()
    missing = [i for i in want if i not in out]
    if missing:
        raise RuntimeError(f'frames {missing[:5]} not found in {src}')
    return {i: full_mask(out[i], w, h) for i in want}, engine.dev or 'cache'


def matte(src, out, device='auto', say=print):
    """every frame of src -> out (the old single-file cutout: projects without work/cutout_plan.json)"""
    r = cut(src, [(0, packets(src), out)], device, None, 1, say)
    return {'frames': r['frames'], 'seconds': r['seconds'], 'device': r['device'], 'fallback_at': r['fallback_at']}


def main():
    skillenv.utf8_stdio()
    if '--info' in sys.argv:
        ok = ort_ready()
        import onnxruntime as ort   # noqa: E402 (after ort_ready loaded the CUDA libraries)
        print(f"onnxruntime {ort.__version__}: {', '.join(ort.get_available_providers())}" if ok else 'onnxruntime missing')
        return
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    device = sys.argv[sys.argv.index('--device') + 1] if '--device' in sys.argv else 'auto'
    if not ort_ready():
        sys.exit('matte: onnxruntime is not installed in the skill venv (setup.py installs it)')
    if not os.path.isfile(MODEL):
        sys.exit(f'matte: model missing ({MODEL}); run setup.py (it fetches it)')
    matte(sys.argv[1], sys.argv[2], device)


if __name__ == '__main__':
    main()
