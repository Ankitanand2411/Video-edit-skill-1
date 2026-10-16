#!/usr/bin/env python3
"""Cut the reel straight from the originals into <project>/assets/aroll.mp4 (1080x1920, clean 30fps CFR from t=0).

Usage:  PY assemble.py <project_dir> [--no-check]      (PY = the skill's Python, see SKILL.md)
First runs check_edl.py: every shot must hold the words its line says (a cut that clips "So I was" off the start of a
line is refused, with the in-point to use instead). --no-check skips that, only after you listened to the shot.
Needs <project>/sources.json (from ingest.py) and <project>/edl.json:
  [{"id": "hook", "clip": "c1", "in": 12.66, "out": 15.72, "zoom": 1.0, "cx": 0.5, "cy": 0.5, "line": "Everybody's..."}, ...]
  zoom > 1 = punch-in cropped from the original (sharp when the source is 4K), centred on (cx, cy) as frame fractions.
Writes segments.json with each segment's first frame in the cut ("frame") and frame count ("frames"), and
assets/voice.wav (lossless, -16.5 LUFS, frame-exact: what render.py mixes) + assets/voice.m4a (preview copy).

Why the CFR re-encode: ffmpeg concat leaves a 0.033s video start offset and timestamp gaps; `hyperframes remove-background`
then duplicates frames and the cutout drifts out of sync with the base video by the end. setpts=N/30 fixes it.
Speed: the shots are cut side by side into lossless intermediates (x264 qp 0, ultrafast: a 6 s shot in 1.1 s instead
of 5.2 s at crf 14), so the a-roll is compressed once, not twice; the voice is levelled while the a-roll encodes.
The intermediates (~13 MB a second of reel) are deleted once aroll.mp4 has every frame.
"""
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')


def size(f):
    w, h = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', f],
                          **skillenv.TEXT).stdout.strip().split(',')[:2]
    return int(w), int(h)


def crop(z, cx, cy, sw, sh):
    if z <= 1:
        return ''
    w, h = round(sw / z / 2) * 2, round(sh / z / 2) * 2
    x = min(max(round(cx * sw - w / 2), 0), sw - w)
    y = min(max(round(cy * sh - h / 2), 0), sh - h)
    return f'crop={w}:{h}:{x}:{y},'


def frames(f):
    """frames without decoding: one packet per frame in these files (~0.1 s instead of decoding the whole file)"""
    return int(subprocess.run([FP, '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_packets',
                               '-of', 'csv=p=0', f], **skillenv.TEXT).stdout.strip().split(',')[0])


def shots_at_once(n, cores):
    """shots cut side by side: each x264 ultrafast keeps ~7 threads busy"""
    return max(1, min(n, (cores or 1) // 4))


def main():
    skillenv.utf8_stdio()
    proj = skillenv.path_arg(sys.argv[1])
    if '--no-check' not in sys.argv:
        import check_edl
        if not check_edl.run(proj):
            sys.exit('assemble.py: the EDL check failed (above). Fix edl.json and run again; --no-check only after listening.')
    work, assets = os.path.join(proj, 'work'), os.path.join(proj, 'assets')
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        src = json.load(fh)
    with open(os.path.join(proj, 'edl.json'), encoding='utf-8') as fh:
        edl = json.load(fh)
    os.makedirs(work, exist_ok=True)
    os.makedirs(assets, exist_ok=True)
    aroll = os.path.join(assets, 'aroll.mp4')
    parts = [os.path.join(work, f'seg_{k}.mp4') for k in range(len(edl))]
    meta = [{**s, 'src_in': s['in'], 'src_out': s['out']} for s in edl]

    def cut(k):
        s, f = edl[k], src[edl[k]['clip']]
        sw, sh = size(f)
        d = s['out'] - s['in']
        # vertical fill: scale to cover 1080x1920 then centre-crop (handles 4K 9:16 and odd phone sizes)
        vf = (f"{crop(s.get('zoom', 1), s.get('cx', .5), s.get('cy', .5), sw, sh)}"
              'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f"{s['in']:.3f}", '-t', f'{d:.3f}', '-i', f,
                        '-map', '0:v:0', '-map', '0:a:0', '-vf', vf,
                        '-af', f'afade=t=in:d=0.02,afade=t=out:st={d - 0.03:.3f}:d=0.03',   # no clicks at the joins
                        '-c:v', 'libx264', '-qp', '0', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',   # lossless
                        '-c:a', 'pcm_s16le', '-ar', '48000', parts[k]], check=True)

    with ThreadPoolExecutor(shots_at_once(len(edl), os.cpu_count())) as ex:
        list(ex.map(cut, range(len(edl))))
    fr = 0
    for k, m in enumerate(meta):   # exact frame of every segment, counted before joining
        n = frames(parts[k])
        m['frame'], m['frames'] = fr, n
        fr += n
    # Audio: each segment's sound trimmed / padded with silence to its picture's exact length, then joined (lossless).
    # A segment's audio is up to a frame shorter than its video; joined as-is the gaps live only in timestamps, and any
    # tool that decodes straight through drops them: the sound then runs ahead of the picture, ~30 ms more per cut
    # (0.67 s by the end of a 21-cut reel). Padding here makes the soundtrack continuous and exact for every consumer.
    wav = os.path.join(work, 'aroll_audio.wav')
    ins, chain = [], []
    for k, (p_, m) in enumerate(zip(parts, meta)):
        ins += ['-i', p_]
        v = m['frames'] / 30
        chain.append(f'[{k}:a]asetpts=PTS-STARTPTS,apad=whole_dur={v:.6f},atrim=end={v:.6f}[a{k}]')
    fc = ';'.join(chain) + ';' + ''.join(f'[a{k}]' for k in range(len(parts))) + f'concat=n={len(parts)}:v=0:a=1[out]'
    subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[out]', '-c:a', 'pcm_s24le', '-ar', '48000', wav],
                   check=True)
    # the list holds bare file names (resolved next to concat.txt), so no drive letters or backslashes end up in it
    concat = os.path.join(work, 'concat.txt')
    with open(concat, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(''.join(skillenv.concat_entry(os.path.basename(p)) for p in parts))
    levelled = []   # the voice is levelled (two loudnorm passes) while the a-roll encodes
    lv = threading.Thread(target=lambda: levelled.append(voice(wav, os.path.join(assets, 'voice.wav'), os.path.join(assets, 'voice.m4a'))))
    lv.start()
    subprocess.run([FF, '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', concat, '-i', wav, '-map', '0:v', '-map', '1:a',
                    '-vf', 'setpts=N/30/TB', '-r', '30', '-fps_mode', 'cfr',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-g', '30', '-keyint_min', '30', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '256k', aroll], check=True)
    lv.join()
    with open(os.path.join(proj, 'segments.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=1)
    for m in meta:
        print(f"frame {m['frame']:4d} ({m['frame'] / 30:6.3f}s) +{m['frames']:3d}f  {m['id']:8s} {m['clip']} {m['in']}-{m['out']}  {m.get('line', '')}")
    total = frames(aroll)
    print(f'total frames {fr} (aroll.mp4 has {total})' + ('' if total == fr else '  << MISMATCH, investigate'))
    if levelled:
        print(levelled[0])
    else:
        sys.exit('assemble.py: levelling the voice failed (see above)')
    if total == fr:   # our own lossless intermediates: ~13 MB a second of reel
        for p_ in parts:
            os.remove(p_)


def voice(src, out_wav, out_m4a, target=-16.5, peak=-2.0):
    """assets/voice.wav: the cut's audio at a steady loudness (two-pass loudnorm, linear: no pumping), LOSSLESS.
    Phone mics often record a voice at -34 LUFS (peaks -11 dB); reels want about -16 with peaks near -2.
    scripts/render.py mixes this file and encodes the reel's audio once; every extra AAC pass costs fidelity (four
    passes measured 31 dB from the lossless mix, one pass 45 dB). assets/voice.m4a is a copy for previews and
    snapshots only."""
    chain = 'highpass=f=70,acompressor=threshold=-30dB:ratio=2.5:attack=8:release=150:makeup=1'
    r = subprocess.run([FF, '-hide_banner', '-i', src, '-vn', '-af', f'{chain},loudnorm=I={target}:TP={peak}:LRA=9:print_format=json',
                        '-f', 'null', '-'], **skillenv.TEXT)
    m = json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])
    lin = (f"loudnorm=I={target}:TP={peak}:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
           f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', src, '-vn', '-af', f'{chain},{lin},aresample=48000', '-c:a', 'pcm_s24le',
                    out_wav], check=True)
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', out_wav, '-c:a', 'aac', '-b:a', '256k', out_m4a], check=True)
    return f"voice.wav: {m['input_i']} LUFS (peak {m['input_tp']} dB) -> {target} LUFS, peak <= {peak} dB (voice.m4a: preview copy)"


if __name__ == '__main__':
    main()
