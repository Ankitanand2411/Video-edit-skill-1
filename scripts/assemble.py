#!/usr/bin/env python3
"""Cut the reel straight from the originals into <project>/assets/aroll.mp4 (1080x1920, clean 30fps CFR from t=0).

Usage:  PY assemble.py <project_dir>      (PY = the skill's Python, see SKILL.md; any Python 3 works for this one)
Needs <project>/sources.json (from ingest.py) and <project>/edl.json:
  [{"id": "hook", "clip": "c1", "in": 12.66, "out": 15.72, "zoom": 1.0, "cx": 0.5, "cy": 0.5, "line": "Everybody's..."}, ...]
  zoom > 1 = punch-in cropped from the original (sharp when the source is 4K), centred on (cx, cy) as frame fractions.
Writes segments.json with each segment's first frame in the cut ("frame") and frame count ("frames"), and
assets/voice.m4a: the cut's audio at a steady -16.5 LUFS (two-pass loudnorm), which the build plays.

Why the CFR re-encode: ffmpeg concat leaves a 0.033s video start offset and timestamp gaps; `hyperframes remove-background`
then duplicates frames and the cutout drifts out of sync with the base video by the end. setpts=N/30 fixes it.
"""
import json
import os
import subprocess
import sys

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
    return int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                               '-of', 'csv=p=0', f], **skillenv.TEXT).stdout.strip().split(',')[0])


def main():
    skillenv.utf8_stdio()
    proj = skillenv.path_arg(sys.argv[1])
    work, assets = os.path.join(proj, 'work'), os.path.join(proj, 'assets')
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        src = json.load(fh)
    with open(os.path.join(proj, 'edl.json'), encoding='utf-8') as fh:
        edl = json.load(fh)
    os.makedirs(work, exist_ok=True)
    os.makedirs(assets, exist_ok=True)
    aroll = os.path.join(assets, 'aroll.mp4')
    parts, meta = [], []
    for k, s in enumerate(edl):
        f = src[s['clip']]
        sw, sh = size(f)
        d = s['out'] - s['in']
        out = os.path.join(work, f'seg_{k}.mp4')
        # vertical fill: scale to cover 1080x1920 then centre-crop (handles 4K 9:16 and odd phone sizes)
        vf = (f"{crop(s.get('zoom', 1), s.get('cx', .5), s.get('cy', .5), sw, sh)}"
              'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f"{s['in']:.3f}", '-t', f'{d:.3f}', '-i', f,
                        '-map', '0:v:0', '-map', '0:a:0', '-vf', vf,
                        '-af', f'afade=t=in:d=0.02,afade=t=out:st={d - 0.03:.3f}:d=0.03',   # no clicks at the joins
                        '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                        '-c:a', 'pcm_s16le', '-ar', '48000', out], check=True)
        parts.append(out)
        meta.append({**s, 'src_in': s['in'], 'src_out': s['out']})
    # the list holds bare file names (resolved next to concat.txt), so no drive letters or backslashes end up in it
    concat = os.path.join(work, 'concat.txt')
    with open(concat, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(''.join(skillenv.concat_entry(os.path.basename(p)) for p in parts))
    subprocess.run([FF, '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
                    '-vf', 'setpts=N/30/TB', '-r', '30', '-fps_mode', 'cfr', '-af', 'asetpts=PTS-STARTPTS',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-g', '30', '-keyint_min', '30', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', aroll], check=True)
    fr = 0
    for k, m in enumerate(meta):
        n = frames(parts[k])
        m['frame'], m['frames'] = fr, n
        fr += n
    with open(os.path.join(proj, 'segments.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=1)
    for m in meta:
        print(f"frame {m['frame']:4d} ({m['frame'] / 30:6.3f}s) +{m['frames']:3d}f  {m['id']:8s} {m['clip']} {m['in']}-{m['out']}  {m.get('line', '')}")
    total = frames(aroll)
    print(f'total frames {fr} (aroll.mp4 has {total})' + ('' if total == fr else '  << MISMATCH, investigate'))
    voice(aroll, os.path.join(assets, 'voice.m4a'))


def voice(aroll, out, target=-16.5, peak=-2.0):
    """assets/voice.m4a: the cut's audio at a steady loudness (two-pass loudnorm, linear: no pumping). Phone mics
    often record a voice at -34 LUFS (peaks -11 dB); reels want about -16 with peaks near -2. The build plays this
    file instead of the a-roll's own track."""
    chain = 'highpass=f=70,acompressor=threshold=-30dB:ratio=2.5:attack=8:release=150:makeup=1'
    r = subprocess.run([FF, '-hide_banner', '-i', aroll, '-vn', '-af', f'{chain},loudnorm=I={target}:TP={peak}:LRA=9:print_format=json',
                        '-f', 'null', '-'], **skillenv.TEXT)
    m = json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])
    lin = (f"loudnorm=I={target}:TP={peak}:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
           f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', aroll, '-vn', '-af', f'{chain},{lin},aresample=48000', '-c:a', 'aac', '-b:a', '192k',
                    out], check=True)
    print(f"voice.m4a: {m['input_i']} LUFS (peak {m['input_tp']} dB) -> {target} LUFS, peak <= {peak} dB")


if __name__ == '__main__':
    main()
