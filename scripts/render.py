#!/usr/bin/env python3
"""Final render, lossless until the last step: <project>/renders/<name>.mp4 (+ the frame-exact audio mix).

Usage (after `PY build.py`):  PY render.py <project_dir> <name> [--crf 12] [--keep-frames]

Why not `HF render` straight to MP4:
  - its MP4 path captures every frame as JPEG (q95 at --quality high) before encoding: a second lossy step that
    softens photos (storyboard pictures) and type. Here frames are captured as PNG (lossless) and encoded once with
    x264 (crf 12, preset slow, BT.709 tagged, 4:2:0 for Instagram).
  - on machines with less than 8 GB of RAM HyperFrames drops to one screenshot worker and its capture can stall for
    good after a few hundred frames (it happened on a 7 GB Linux box at frame 537, then 169, then 348 of a chunk).
    So the reel renders in sessions of fresh Chrome: every finished frame is hard-linked into renders/<name>_frames/
    while the session runs (HyperFrames deletes its work folder when it fails), a watchdog kills a session that
    delivers no frame for STALL seconds, and the next session starts at the first missing frame. Nothing captured is
    ever thrown away.

Needs build.py to support `--range A B` (writes chunk_<first frame>.html covering [A, B), no audio elements) and to
write work/reel.json {"reel_dur", "frames", "sfx": [{"name", "t", "dur", "vol"}]} (the template's build.py does both).
Audio: assets/voice.wav (assemble.py, lossless; voice.m4a for older projects) + the SFX at their composition gains + an optional music bed
(assets/music.mp3|m4a|wav, looped, faded, ducked under the voice with a sidechain compressor).
"""
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

STALL, BOOT, SESSION = 40, 180, 150    # s without a new frame / s to the first frame / max frames per session
MUSIC_GAIN = 0.20                      # music bed under the voice (before ducking): ~-14 dB, then ducked ~8 dB more


def complete_png(p):
    try:
        with open(p, 'rb') as fh:
            fh.seek(-12, 2)
            return b'IEND' in fh.read()
    except OSError:
        return False


def chrome_pids():
    """headless Chrome processes running now (POSIX). Puppeteer starts Chrome detached, outside our process group."""
    if os.name == 'nt':
        return set()
    out = subprocess.run(['ps', '-eo', 'pid=,args='], **skillenv.TEXT).stdout
    return {int(l.split(None, 1)[0]) for l in out.splitlines() if 'chrome-headless-shell' in l or 'puppeteer_dev_chrome_profile' in l}


def kill_session(proc, before):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    for pid in chrome_pids() - before:   # only the Chrome this session started
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def link(src, dst):
    try:
        os.link(src, dst)
    except OSError:   # other filesystem / no hard links: copy
        shutil.copyfile(src, dst)


def frames_of(proj, name, total):
    cdir, safe = os.path.join(proj, 'renders', f'{name}_work'), os.path.join(proj, 'renders', f'{name}_frames')
    os.makedirs(safe, exist_ok=True)
    have = lambda n: os.path.exists(os.path.join(safe, f'{n:05d}.png'))
    start = 0
    while True:
        while start < total and have(start):
            start += 1
        if start >= total:
            return safe
        end = start + 1   # up to SESSION frames, stopping at the next frame already captured
        while end < total and end - start < SESSION and not have(end):
            end += 1
        subprocess.run([sys.executable, 'build.py', '--range', f'{start / 30:.6f}', f'{end / 30:.6f}'], cwd=proj, check=True,
                       capture_output=True)
        html = f'chunk_{start:05d}.html'
        log = os.path.join(proj, 'work', f'render_{name}_{start:05d}.log')
        os.makedirs(os.path.dirname(log), exist_ok=True)
        argv, env = skillenv.hyperframes_command(['render', '-c', html, '--format', 'png-sequence', '-o',
                                                  os.path.relpath(os.path.join(cdir, f's{start:05d}'), proj), '--quality', 'high'])
        env.setdefault('HF_DE_STALL_MS', '120000')   # our own watchdog acts first
        before_dirs, before_chrome = set(glob.glob(os.path.join(cdir, 'work-*'))), chrome_pids()
        print(f'session from frame {start} ({start / 30:.2f}s)', flush=True)
        got, t0 = 0, time.time()
        with open(log, 'w', encoding='utf-8') as fh:
            kw = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            proc = subprocess.Popen(argv, cwd=proj, env=env, stdout=fh, stderr=subprocess.STDOUT, **kw)
            last_new = time.time()
            while proc.poll() is None:
                time.sleep(2)
                for wd in set(glob.glob(os.path.join(cdir, 'work-*'))) - before_dirs:
                    for p in glob.glob(os.path.join(wd, 'captured-frames', 'frame_*.png')):
                        n = start + int(os.path.basename(p)[6:12])
                        if n < end and not have(n) and complete_png(p):
                            link(p, os.path.join(safe, f'{n:05d}.png')); got += 1; last_new = time.time()
                if time.time() - last_new > (STALL if got else BOOT):
                    print(f'   stalled after {got} frames: next session starts at the first missing frame', flush=True)
                    kill_session(proc, before_chrome)
                    break
            proc.wait()
        # a session that finished: its output folder is the authority (live links can catch a frame mid-flight).
        # Numbering differs: the work folder counts from 0 (frame_000000), the output folder from 1 (frame_000001).
        for p in glob.glob(os.path.join(cdir, f's{start:05d}', '**', '*.png'), recursive=True):
            digits = ''.join(ch for ch in os.path.basename(p) if ch.isdigit())
            n = start + int(digits) - 1 if digits else -1
            if start <= n < end and complete_png(p):
                dst = os.path.join(safe, f'{n:05d}.png')
                got += 0 if have(n) else 1
                if os.path.exists(dst):
                    os.remove(dst)
                link(p, dst)
        print(f'   +{got} frames ({time.time() - t0:.0f}s)', flush=True)
        if os.path.exists(os.path.join(proj, html)):
            os.remove(os.path.join(proj, html))
        if got == 0 and not have(start):
            sys.exit(f'no progress from frame {start}: see {log}')


def audio_mix(proj, reel, out):
    ff = skillenv.tool('ffmpeg')
    wav = os.path.join(proj, 'assets', 'voice.wav')   # lossless and frame-exact (assemble.py); the .m4a only on older projects
    ins, flt = ['-i', wav if os.path.isfile(wav) else os.path.join(proj, 'assets', 'voice.m4a')], []
    for k, s in enumerate(reel['sfx']):
        ins += ['-i', os.path.join(proj, 'assets', 'sfx', f"{s['name']}.mp3")]
        ms = int(round(s['t'] * 1000))
        flt.append(f"[{k + 1}:a]atrim=0:{s['dur']},volume={s['vol']},adelay={ms}|{ms},aresample=48000[s{k}]")
    dur = reel['reel_dur']
    voice = f"[0:a]aresample=48000,apad=whole_dur={dur}"
    music = next((p for p in (os.path.join(proj, 'assets', f'music.{e}') for e in ('mp3', 'm4a', 'wav')) if os.path.isfile(p)), None)
    mixed = [f'[s{k}]' for k in range(len(reel['sfx']))]
    if music:   # loop, trim, fade, then duck under the voice
        mi = len(reel['sfx']) + 1
        ins += ['-stream_loop', '-1', '-i', music]
        flt.append(f"[{mi}:a]atrim=0:{dur},aresample=48000,volume={MUSIC_GAIN},afade=t=in:d=.6,afade=t=out:st={dur - 1.8}:d=1.8[mus]")
        voice += ',asplit=2[v][key]'
        flt.append('[mus][key]sidechaincompress=threshold=0.04:ratio=6:attack=25:release=450[duck]')
        mixed.append('[duck]')
    else:
        voice += '[v]'
    fc = ';'.join([voice] + flt) + ';[v]' + ''.join(mixed) + f'amix=inputs={len(mixed) + 1}:normalize=0:duration=first,alimiter=limit=0.89[a]'
    subprocess.run([ff, '-v', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[a]', '-c:a', 'pcm_s16le', out], check=True)
    return music


def main():
    skillenv.utf8_stdio()
    proj, name = skillenv.path_arg(sys.argv[1]), sys.argv[2]
    crf = sys.argv[sys.argv.index('--crf') + 1] if '--crf' in sys.argv else '12'
    with open(os.path.join(proj, 'work', 'reel.json'), encoding='utf-8') as fh:
        reel = json.load(fh)
    total = reel['frames']
    t0 = time.time()
    safe = frames_of(proj, name, total)
    wav = os.path.join(proj, 'work', f'{name}_audio.wav')
    music = audio_mix(proj, reel, wav)
    out = os.path.join(proj, 'renders', f'{name}.mp4')
    subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', '-y', '-framerate', '30', '-i', os.path.join(safe, '%05d.png'), '-i', wav,
                    '-map', '0:v', '-map', '1:a',
                    '-vf', 'scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', crf, '-profile:v', 'high', '-tune', 'film',
                    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                    '-c:a', 'aac', '-b:a', '320k', '-frames:v', str(total), '-movflags', '+faststart', out], check=True)   # the one lossy audio pass
    n = int(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                            'stream=nb_read_frames', '-of', 'csv=p=0', out], **skillenv.TEXT).stdout.strip() or 0)
    if n == total and '--keep-frames' not in sys.argv:   # our own intermediates: ~1.4 MB a frame
        shutil.rmtree(safe, ignore_errors=True)
        shutil.rmtree(os.path.join(proj, 'renders', f'{name}_work'), ignore_errors=True)
    print(f"wrote {out}: {n}/{total} frames, crf {crf}{', music bed ' + os.path.basename(music) if music else ''} "
          f"({(time.time() - t0) / 60:.1f} min)")


if __name__ == '__main__':
    main()
