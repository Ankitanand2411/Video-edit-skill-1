#!/usr/bin/env python3
"""GPU support for the cutout (matte.py) and Whisper: one time per machine, inside the skill's venv. Nothing
system-wide, no PATH change, no restart. setup.py runs this (it needs the venv's Python):

  PY gpu.py             report: STATUS lines, repairs a broken install from pip's cache, last line "GPU {json}"
  PY gpu.py --install   also installs what this machine can use (asks the user first: ~1.7 GB with an NVIDIA GPU)

What each machine gets (versions proven together on a GTX 1650, driver 595 / CUDA 13.2, Linux):
  NVIDIA (Linux, Windows)  CUDA 12 + cuDNN 9.10 libraries from PyPI (nvidia-*-cu12, ~1.5 GB) + onnxruntime-gpu 1.22:
                           cutout and Whisper on the GPU. onnxruntime-gpu 1.31 wants CUDA 13; cuDNN 9.27 fails on
                           Turing ("No valid engine configs for ConvFwd"): hence the pins.
  Windows, other GPUs      onnxruntime-directml (~25 MB): cutout on any DirectX 12 GPU (AMD, Intel); Whisper on the CPU
  Mac                      nothing: HyperFrames' cutout already runs on the Apple GPU (CoreML); Whisper on the CPU
  no usable GPU            nothing: everything on the CPU, as before
An NVIDIA card without its driver is left alone (installing a driver needs admin rights and a reboot).
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

CUDA_PACKAGES = ['nvidia-cuda-runtime-cu12==12.9.79', 'nvidia-cuda-nvrtc-cu12==12.9.86', 'nvidia-nvjitlink-cu12==12.9.86',
                 'nvidia-cublas-cu12==12.9.2.10', 'nvidia-cudnn-cu12==9.10.2.21', 'nvidia-cufft-cu12==11.4.1.4',
                 'nvidia-curand-cu12==10.3.10.19']
ORT = {'cuda': 'onnxruntime-gpu==1.22.0', 'dml': 'onnxruntime-directml==1.22.0'}
DOWNLOAD_MB = {'cuda': 1700, 'dml': 25}


def say(line):
    print(line, flush=True)


# ------------------------------------------------------------------ pure parts (unit-tested)
def parse_nvidia_smi(text):
    """`nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader` -> {name, vram_mb, driver} or None"""
    line = next((l for l in text.splitlines() if l.strip()), '')
    parts = [p.strip() for p in line.split(',')]
    if len(parts) < 3 or not parts[0]:
        return None
    mb = int(''.join(ch for ch in parts[1] if ch.isdigit()) or 0)
    return {'name': parts[0], 'vram_mb': mb, 'driver': parts[2]}


def plan(osn, nvidia):
    """-> 'cuda' | 'dml' | None: the GPU path this machine gets"""
    if osn == 'macos':
        return None
    if nvidia:
        return 'cuda'
    return 'dml' if osn == 'windows' else None


def packages(path):
    return (CUDA_PACKAGES + [ORT['cuda']]) if path == 'cuda' else [ORT['dml']] if path == 'dml' else []


# ------------------------------------------------------------------ the machine
def nvidia():
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
                           timeout=20, **skillenv.TEXT)
        return parse_nvidia_smi(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cutout_device(path):
    """run the cutout model once on the GPU path (fallback off): 'cuda' / 'dml' when it really computed there"""
    code = ('import sys; sys.path.insert(0, %r); import matte, numpy as np\n'
            'matte.ort_ready(); s, dev = matte.session(%r)\n'
            'y = matte.run(s, np.zeros((1, 3, 320, 320), np.float32)); print("DEV", dev if s.get_providers()[0] == matte.PROVIDER[%r] else "cpu")'
            % (os.path.dirname(os.path.abspath(__file__)), path, path))
    r = subprocess.run([sys.executable, '-c', code], timeout=300, **skillenv.TEXT)   # own process: a crash stays there
    out = [l for l in r.stdout.splitlines() if l.startswith('DEV ')]
    return out[-1].split()[1] if out and out[-1].split()[1] == path else None


WHISPER_TEST = (
    'import sys; sys.path.insert(0, %r); import skillenv, numpy as np\n'
    'dev = skillenv.whisper_device()\n'
    'if dev == "cuda":\n'
    '    from faster_whisper import WhisperModel\n'
    '    try:\n'
    '        m = WhisperModel("small.en", device="cuda", compute_type="int8", local_files_only=True)\n'
    '    except Exception:\n'
    '        m = None   # model not downloaded yet: the library check has to do\n'
    '    if m is not None:   # cuBLAS / cuDNN are only loaded by the first transcription\n'
    '        list(m.transcribe(np.zeros(16000, np.float32), beam_size=1, without_timestamps=True)[0])\n'
    'print("DEV", dev)')


def whisper_device():
    """'cuda' only when Whisper really transcribes there: one second of silence through small.en on the GPU. The
    library check alone passed on a Windows PC whose first real transcription then could not load cuBLAS."""
    try:
        r = subprocess.run([sys.executable, '-c', WHISPER_TEST % os.path.dirname(os.path.abspath(__file__))], timeout=180,
                           **skillenv.TEXT)
    except subprocess.TimeoutExpired:
        return 'cpu'
    out = [l for l in r.stdout.splitlines() if l.startswith('DEV ')]
    return out[-1].split()[1] if out and r.returncode == 0 else 'cpu'


def pip(args):
    return subprocess.run([sys.executable, '-m', 'pip', '-q', '--disable-pip-version-check'] + args, **skillenv.TEXT)


def installed(path):
    out = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=json', '--disable-pip-version-check'],
                         **skillenv.TEXT).stdout   # not pip(): -q silences the list itself
    have = {p['name'].lower() for p in json.loads(out or '[]')}
    return all(p.split('==')[0].lower() in have for p in packages(path))


def install(path):
    """the pinned packages; the CPU-only onnxruntime goes (it shares files with the GPU build and would win)"""
    pip(['uninstall', '-y', 'onnxruntime'])
    r = pip(['install'] + packages(path))
    if r.returncode == 0:   # files of the GPU build last, whatever pip resolved before
        r = pip(['install', '--force-reinstall', '--no-deps', ORT[path]])
    return r.returncode == 0, (r.stdout + r.stderr)[-800:]


def main():
    skillenv.utf8_stdio()
    osn = skillenv.detect()['os']
    card = nvidia()
    path = plan(osn, card)
    rec = {'card': card and card['name'], 'vram_mb': card and card['vram_mb'], 'path': path, 'cutout': None, 'whisper': 'cpu'}
    if osn == 'macos':
        say('STATUS gpu Mac: the cutout already runs on the Apple GPU (HyperFrames CoreML); Whisper on the CPU')
    elif not path:
        say('STATUS gpu none usable (no NVIDIA GPU with its driver): cutout and Whisper on the CPU, as before')
    else:
        what = f"{card['name']} ({card['vram_mb']} MB)" if card else 'DirectX 12 GPU'
        if '--install' in sys.argv and not installed(path):
            say(f'STATUS gpu installing GPU support for {what} (one time, ~{DOWNLOAD_MB[path]} MB, no restart)...')
            t0 = time.time()
            ok, log = install(path)
            say(f'STATUS gpu install {"done" if ok else "FAILED"} in {time.time() - t0:.0f}s' + ('' if ok else f'\n{log}'))
        if installed(path):
            rec['cutout'] = cutout_device(path)
            if not rec['cutout']:   # pip put the CPU-only onnxruntime back (a venv repair): the GPU build again, from cache
                pip(['install', '--force-reinstall', '--no-deps', ORT[path]])
                rec['cutout'] = cutout_device(path)
            rec['whisper'] = whisper_device() if path == 'cuda' else 'cpu'
            if rec['cutout']:
                say(f"STATUS gpu OK: {what}: cutout on {rec['cutout'].upper()}, Whisper on {rec['whisper'].upper()}")
            else:
                say(f'STATUS gpu INSTALLED BUT NOT WORKING on {what}: cutout and Whisper stay on the CPU '
                    f'(safe). Run `PY setup.py --gpu` again; if it persists, update the GPU driver')
        else:
            say(f'STATUS gpu AVAILABLE: {what} can run the cutout{" and Whisper" if path == "cuda" else ""} several times '
                f'faster -> one-time install: PY setup.py --gpu (~{DOWNLOAD_MB[path]} MB into the skill folder, no restart). '
                f'Optional: without it everything runs on the CPU')
    print('GPU ' + json.dumps(rec), flush=True)


if __name__ == '__main__':
    main()
