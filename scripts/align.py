#!/usr/bin/env python3
"""Word timings for the cut, anchored shot by shot -> <project>/words.json (replaces transcribe_cut.py).

Usage:  PY align.py <project_dir> [small.en|medium.en]

Whisper's word times drift on a long cut (0.5-0.8s early by the end of a 60s reel: words land before their own shot).
Here every segment's audio is transcribed on its own, so each word is anchored to its shot's exact first frame; the
TEXT comes from edl.json "line" (write what was actually said there, with punctuation: it drives the caption breaks),
Whisper only supplies the times. Words Whisper did not hear get times interpolated between their neighbours (flagged).
Each word carries "seg" (its segment id). Reads assets/voice.m4a if present (cleaner levels), else assets/aroll.mp4.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402


def norm(t):
    return re.sub(r"[^\w']", '', t.lower().replace('-', ''))


def main():
    skillenv.utf8_stdio()
    proj = skillenv.path_arg(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else 'small.en'
    with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
        segs = json.load(fh)
    with open(os.path.join(proj, 'edl.json'), encoding='utf-8') as fh:
        edl = {s['id']: s for s in json.load(fh)}
    src = os.path.join(proj, 'assets', 'voice.m4a')
    src = src if os.path.isfile(src) else os.path.join(proj, 'assets', 'aroll.mp4')
    wav = os.path.join(proj, 'work', 'seg.wav')
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    m = skillenv.whisper(model)
    out = []
    for s in segs:
        a, d = s['frame'] / 30, s['frames'] / 30
        subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', '-y', '-ss', f'{a:.3f}', '-t', f'{d:.3f}', '-i', src, '-ac', '1',
                        '-ar', '16000', wav], check=True)
        line = edl[s['id']].get('line', '')
        r, _ = m.transcribe(wav, word_timestamps=True, vad_filter=False, initial_prompt=line or None)
        heard = [w for x in r for w in x.words]
        want = line.split() or [w.word.strip() for w in heard]
        got = [norm(w.word) for w in heard]
        times, j = [], 0
        for wd in want:   # greedy match in order; Whisper splits / merges some tokens ("old" "-fashioned")
            k = next((k for k in range(j, min(j + 4, len(heard))) if got[k] and (got[k] == norm(wd) or norm(wd).startswith(got[k]))), None)
            if k is None:
                times.append(None)
                continue
            times.append((heard[k].start, heard[k].end))
            j = k + 1
        ok = sum(t is not None for t in times)
        for i, t in enumerate(times):   # fill the gaps between known neighbours
            if t is None:
                prev = next((times[p][1] for p in range(i - 1, -1, -1) if times[p]), 0.0)
                nxt = next((times[q][0] for q in range(i + 1, len(times)) if times[q]), d)
                times[i] = (prev, max(prev + .05, nxt))
        for wd, (st, en) in zip(want, times):
            out.append({'text': wd, 'start': round(a + max(st, .02), 3), 'end': round(a + min(en, d), 3), 'seg': s['id']})
        flag = '' if ok == len(want) else f'   << {ok}/{len(want)} heard; Whisper: {" ".join(w.word.strip() for w in heard)}'
        print(f"{s['id']} {a:6.2f}  " + ' '.join(f"{w}@{a + st:.2f}" for w, (st, _) in zip(want, times)) + flag, flush=True)
    with open(os.path.join(proj, 'words.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
