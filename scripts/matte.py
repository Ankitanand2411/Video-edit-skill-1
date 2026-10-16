#!/usr/bin/env python3
"""The skill's own background removal: HyperFrames' remove-background recipe (same model file, same steps, same VP9
encode) run through onnxruntime for Python, so the cutout can use the GPU on every OS:
CUDA (NVIDIA, Linux and Windows), DirectML (any DirectX 12 GPU on Windows: NVIDIA, AMD, Intel), CoreML (Mac).
HyperFrames 0.8.34 itself offers CUDA on Linux only (its Windows build ships DirectML but no way to choose it) and
CoreML on Apple Silicon only.

Usage:  PY matte.py <input.mp4> <output.webm> [--device auto|cuda|dml|coreml|cpu]
        (cutout.py calls it; `--info` prints what this machine can run it on)

Recipe (hyperframes@0.8.34 dist/cli.js: background-removal/inference.ts + pipeline.ts):
  ffmpeg decode rgb24 -> lanczos3 resize to 320x320 -> divide by the brightest value -> (x - mean) / std (ImageNet)
  -> u2net_human_seg -> first output plane min-max to 0..255 -> lanczos3 resize to the frame -> alpha
  -> ffmpeg VP9 crf 12 ("best"), deadline good, cpu-used 4, row-mt, yuva420p, BT.709 tags, alpha_mode=1.
Before the clip, frame 0 is matted on the GPU and on the CPU and the masks compared (self-test): a GPU path that does
not match is not used. A GPU error on frame N re-runs frame N on the CPU and the rest of the clip stays there: nothing
already encoded is lost. Prints the device and frames/s.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

MODEL = os.path.join(os.path.expanduser('~'), '.cache', 'hyperframes', 'background-removal', 'models', 'u2net_human_seg.onnx')
SIZE = 320
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
CRF = 12             # HyperFrames QUALITY_CRF['best'], what cutout.py asks for
SELFTEST_DB = 40.0   # GPU mask vs CPU mask on frame 0, PSNR of the alpha
PROVIDER = {'cuda': 'CUDAExecutionProvider', 'dml': 'DmlExecutionProvider', 'coreml': 'CoreMLExecutionProvider',
            'cpu': 'CPUExecutionProvider'}


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


def preprocess(rgb):
    """HxWx3 uint8 frame -> 1x3x320x320 float32 tensor, as HyperFrames' preprocess()"""
    import numpy as np
    from PIL import Image
    small = np.asarray(Image.fromarray(rgb).resize((SIZE, SIZE), Image.LANCZOS), dtype=np.float32)
    small = small / max(float(small.max()), 1.0)
    small = (small - np.array(MEAN, np.float32)) / np.array(STD, np.float32)
    return np.ascontiguousarray(small.transpose(2, 0, 1)[None], dtype=np.float32)


def mask_of(out, width, height):
    """model output -> HxW uint8 alpha, as HyperFrames' postprocess(): min-max of the first plane, round, resize"""
    import numpy as np
    from PIL import Image
    plane = np.asarray(out, dtype=np.float32).reshape(-1)[:SIZE * SIZE].reshape(SIZE, SIZE)
    lo, hi = float(plane.min()), float(plane.max())
    m = np.clip(np.round((plane - lo) / ((hi - lo) or 1.0) * 255.0), 0, 255).astype(np.uint8)
    return np.asarray(Image.fromarray(m, 'L').resize((width, height), Image.LANCZOS))


def psnr(a, b):
    import numpy as np
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def encoder_args(ff, width, height, fps, out, crf=CRF):
    return [ff, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{width}x{height}', '-r', str(fps), '-i', '-',
            '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', str(crf), '-deadline', 'good', '-row-mt', '1', '-cpu-used', '4',
            '-auto-alt-ref', '0', '-pix_fmt', 'yuva420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc',
            'bt709', '-color_range', 'tv', '-metadata:s:v:0', 'alpha_mode=1', '-an', out]


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
                return s, dev
            say(f'matte: {dev} self-test FAILED (mask {db:.1f} dB vs the CPU, need {SELFTEST_DB:.0f}): not used')
        except Exception as e:   # driver, library, out of memory: this provider is out
            say(f'matte: {dev} failed to start ({str(e).splitlines()[0][:160]})')
    return cpu, 'cpu'


# ------------------------------------------------------------------ the clip
def probe(path):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout.strip().split(',')
    num, den = out[2].split('/')
    return int(out[0]), int(out[1]), round(int(num) / int(den), 3)


def compose(frame, y):
    """RGBA bytes for the encoder: the frame with the mask as alpha (HyperFrames' applyMask)"""
    import numpy as np
    h, w = frame.shape[:2]
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = frame
    rgba[..., 3] = mask_of(y, w, h)
    return rgba.tobytes()


DEPTH = 3   # frames in flight on each side of the model: resizing (CPU threads) overlaps the inference (GPU)


def matte(src, out, device='auto', say=print):
    """-> {'frames', 'seconds', 'device', 'fallback_at'}. Frames go through in order: CPU threads resize frame n+1
    and finish frame n-1 while the model runs on frame n (one after another the GPU sat idle half the time)."""
    import collections
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    w, h, fps = probe(src)
    ff = skillenv.tool('ffmpeg')
    dec = subprocess.Popen([ff, '-loglevel', 'error', '-i', src, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-an', '-'],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(encoder_args(ff, w, h, fps, out), stdin=subprocess.PIPE)
    nbytes = w * h * 3
    info = skillenv.detect()
    st = {'s': None, 'dev': 'cpu', 'cpu': None, 'fallback_at': None}
    n, t0, shown = 0, time.time(), time.time()
    pool = ThreadPoolExecutor(max_workers=max(2, min(6, (os.cpu_count() or 2) - 1)))
    pre, post = collections.deque(), collections.deque()

    def infer(idx, t):
        try:
            return run(st['s'], t)
        except Exception as e:   # GPU trouble mid-clip: this frame and the rest on the CPU
            if st['dev'] == 'cpu':
                raise
            say(f"matte: {st['dev']} failed at frame {idx} ({str(e).splitlines()[0][:120]}): continuing on the CPU")
            st['cpu'] = st['cpu'] or session('cpu')[0]
            st.update(s=st['cpu'], dev='cpu', fallback_at=idx)
            return run(st['s'], t)

    def frames():
        while True:
            buf = dec.stdout.read(nbytes)
            if len(buf) < nbytes:
                return
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)

    def step():   # oldest prepared frame through the model; its compositing goes to the pool
        nonlocal n, shown
        idx, frame, fut = pre.popleft()
        post.append(pool.submit(compose, frame, infer(idx, fut.result())))
        while len(post) > DEPTH:
            enc.stdin.write(post.popleft().result())
        n += 1
        if time.time() - shown >= 30:
            shown = time.time()
            say(f"matte: {n} frames, {n / (shown - t0):.2f} frames/s on {st['dev']}")

    try:
        for idx, frame in enumerate(frames()):
            if st['s'] is None:   # first frame: choose the device (self-test against the CPU)
                st['s'], st['dev'] = pick(info['os'], info['arch'], frame, say) if device == 'auto' else session(device)
            pre.append((idx, frame, pool.submit(preprocess, frame)))
            if len(pre) > DEPTH:
                step()
        while pre:
            step()
        while post:
            enc.stdin.write(post.popleft().result())
    finally:
        pool.shutdown(wait=True)
        enc.stdin.close()
        enc.wait()
        dec.stdout.close()
        dec.wait()
    dev, fallback_at = st['dev'], st['fallback_at']
    if enc.returncode:
        raise RuntimeError(f'VP9 encoder failed (exit {enc.returncode})')
    dt = time.time() - t0
    say(f'matte: {n} frames in {dt:.0f}s ({n / max(dt, .01):.2f} frames/s) on {dev}'
        + (f' (GPU until frame {fallback_at}, CPU after)' if fallback_at is not None else ''))
    return {'frames': n, 'seconds': dt, 'device': dev, 'fallback_at': fallback_at}


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
        sys.exit('matte: onnxruntime is not installed in the skill venv (setup.py --gpu installs the right build)')
    if not os.path.isfile(MODEL):
        sys.exit(f'matte: model missing ({MODEL}); run setup.py (it fetches it)')
    matte(sys.argv[1], sys.argv[2], device)


if __name__ == '__main__':
    main()
