#!/usr/bin/env python3
"""Check the EDL against the audio BEFORE anything is cut: every shot must hold the words its line says, and every
word the cut drops is printed for the editor to see. assemble.py runs this first and refuses an EDL that fails.

Usage:  PY check_edl.py <project_dir> [--edl other.json] [--model small.en]
        (assemble.py <project> runs it automatically; --no-check skips it there, after you listened)

Why it exists: the first cool girl reel opened on "actually really curious" although its line read "I was actually
really curious about handwriting". "So I was" is said in 0.3s, then a 0.4s pause; the in-point was put after the
pause, taking "So I was" for "So". align.py printed "5/7 heard" for that shot and it was waved off as Whisper missing
fast words (a real gotcha, wrongly applied): the words were not in the shot at all.

Per shot (times are the source clip's):
  1. transcribe the shot's own audio [in, out] and match it to the line, in order.
  2. line words missing at the START with no other word heard in their place -> transcribe again with the 1.5s
     before the in-point. Found there: FAIL, the in-point clips them (prints the speech onset to start at instead).
     Not found anywhere: FAIL too, the caption would show words the audio does not have; if someone listened and
     they are there, list them in the segment's "heard_ok". A different word heard in their place ("were" heard as
     "or") is a mishearing: fine, captions take their text from the line.
  3. the same at the END with the 1.0s after the out-point.
  4. notes: a cut point inside continuous sound (a word may be clipped: the nearest silence is printed) and words
     heard inside the shot before the line's first / after its last word (a false start let in, or Whisper inventing
     a word at a cut).
Then a DROPPED report: what is said in every stretch the EDL leaves out between shots of a clip (up to 20s each).
Read it next to the EDL table: a sentence start in there ("So I was") is exactly the mistake above.
Exit 1 when any shot fails. A passing EDL is remembered (work/edl_check.json) so re-assembling does not re-run it.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

SR = 16000
LEAD_PAD, TRAIL_PAD = 1.5, 1.0   # how far outside a cut to look for the words it may clip
GAP_MAX = 20.0                   # dropped stretches longer than this are unused footage, not a trim


# ------------------------------------------------------------------ pure logic (unit-tested)
def norm(t):
    return re.sub(r"[^\w']", '', t.lower().replace('-', ''))


def match(want, got, look=4):
    """in-order greedy match of line words to heard words (both normalised) -> heard index or None per line word.
    A heard word may be a prefix of the line word: Whisper splits "old-fashioned" into "old" "-fashioned"."""
    out, j = [], 0
    for w in want:
        k = next((k for k in range(j, min(j + look, len(got))) if got[k] and (got[k] == w or w.startswith(got[k]))), None)
        out.append(k)
        if k is not None:
            j = k + 1
    return out


def clean(heard):
    """Whisper splits "old-fashioned" into "old" "-fashioned." and emits bare "-" tokens: glue the first back onto its
    word, drop tokens with no letters. Takes and returns [str] or [(text, start, end)]."""
    out = []
    for h in heard:
        t = h if isinstance(h, str) else h[0]
        if not norm(t):
            continue
        if out and t.startswith('-'):
            p = out[-1]
            out[-1] = p + t if isinstance(p, str) else (p[0] + t, p[1], h[2])
            continue
        out.append(h)
    return out


def edges(line_words, heard_words):
    """-> (lead_missing, lead_extra, trail_missing, trail_extra): line words before the first / after the last word
    that was heard, and heard words before / after the matched run"""
    heard_words = clean(heard_words)
    m = match([norm(w) for w in line_words], [norm(h) for h in heard_words])
    hit = [i for i, k in enumerate(m) if k is not None]
    if not hit:
        return list(line_words), list(heard_words), [], []
    f, last = hit[0], hit[-1]
    return line_words[:f], heard_words[:m[f]], line_words[last + 1:], heard_words[m[last] + 1:]


def side_status(missing, extra, heard_ok=()):
    """'ok' | 'misheard' (another word was heard in their place) | 'missing' (nothing in their place)"""
    ok = {norm(w) for w in heard_ok}
    missing = [w for w in missing if norm(w) not in ok]
    if not missing:
        return 'ok'
    return 'misheard' if len(extra) >= len(missing) else 'missing'


def clipped(missing, heard, side, cut):
    """missing = the line's first ('lead') or last ('trail') words the shot does not hold; heard = [(text, start, end)]
    transcribed across the cut (source times). -> [(word, start, end)] of those said just outside it, searched outward
    from the cut so the occurrence nearest to it counts (an earlier sentence may repeat a word)"""
    heard = clean(heard)
    if side == 'lead':
        words, near = missing[::-1], [h for h in heard if h[1] < cut - .03][::-1]
    else:
        words, near = missing, [h for h in heard if h[2] > cut + .03]
    m = match([norm(w) for w in words], [norm(h[0]) for h in near], look=2)   # each within 2 heard words of the last
    out = [(w, near[k][1], near[k][2]) for w, k in zip(words, m) if k is not None]
    return out[::-1] if side == 'lead' else out


def islands(db, hop=.02, thr=-45.0, min_gap=.08, t0=0.0):
    """speech stretches from an RMS envelope (dB per hop): above thr, silences shorter than min_gap bridged"""
    out, start, quiet = [], None, 0
    for i, v in enumerate(db):
        t = t0 + i * hop
        if v > thr:
            if start is None:
                start = t
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet * hop >= min_gap:
                out.append((round(start, 3), round(t - (quiet - 1) * hop, 3)))
                start, quiet = None, 0
    if start is not None:
        out.append((round(start, 3), round(t0 + len(db) * hop - quiet * hop, 3)))
    return out


def island_at(isl, t, side):
    """the speech stretch holding time t (or the nearest one before it for 'lead', after it for 'trail')"""
    hold = [s for s in isl if s[0] - .05 <= t <= s[1] + .05]
    if hold:
        return hold[0]
    near = [s for s in isl if s[1] <= t] if side == 'lead' else [s for s in isl if s[0] >= t]
    return (near[-1] if side == 'lead' else near[0]) if near else None


def inside_sound(isl, t, kind, depth=.15):
    """the speech stretch an in-point ('in') cuts the start off, or an out-point ('out') cuts the end off, by depth s
    or more (a word may be clipped). The last few hundredths of a word dying away are not a clipped word: on the first
    real run 12 of 20 out-points were flagged for 0.04-0.12s of decay."""
    if kind == 'in':
        return next((s for s in isl if s[0] + depth <= t < s[1]), None)
    return next((s for s in isl if s[0] < t <= s[1] - depth), None)


def drop_words(heard, a, b, isl, slack=.15):
    """the words said in a dropped stretch [a, b]: heard across it with context on both sides, kept when their middle
    is inside the stretch AND they sit on sound that belongs to it (a stretch of sound that starts and ends inside
    the gap, not the edge of the kept shots' speech). On the first run Whisper filled near-silent gaps with "Thank you
    for watching!", and the next shot's first word ("and", "writing"), stamped early into the pause, leaked in."""
    near = [(max(s[0] - slack, a), min(s[1] + slack, b)) for s in isl if s[0] < b - .05 and s[1] > a + .05]
    keep = []
    for h in clean(heard):
        mid = (h[1] + h[2]) / 2
        if a <= mid <= b and any(min(h[2], z[1]) - max(h[1], z[0]) >= .03 for z in near):
            keep.append(h)
    return keep


def gaps(edl, clip_len):
    """stretches of each clip the EDL leaves out between consecutive shots (in source order), plus the head and tail
    -> [(clip, a, b, before_id, after_id)], only those up to GAP_MAX long"""
    out = []
    for clip in dict.fromkeys(s['clip'] for s in edl):
        segs = sorted((s for s in edl if s['clip'] == clip), key=lambda s: s['in'])
        prev_out, prev_id = 0.0, None
        for s in segs:
            if .15 < s['in'] - prev_out <= GAP_MAX:
                out.append((clip, round(prev_out, 3), round(s['in'], 3), prev_id, s['id']))
            if s['out'] > prev_out:
                prev_out, prev_id = s['out'], s['id']
        end = clip_len.get(clip)
        if end and .15 < end - prev_out <= GAP_MAX:
            out.append((clip, round(prev_out, 3), round(end, 3), prev_id, None))
    return out


def trim_kept(dropped, before_words, after_words):
    """drop-report words minus the neighbouring shots' own edge words whose soft start or end spills into the gap
    ("fingers" | so holding up | "because"). Safe: a line word really cut off fails that shot's own check."""
    d = list(dropped)
    nb, na = [norm(w) for w in before_words], [norm(w) for w in after_words]
    lead = max((n for n in range(1, min(len(d), len(nb)) + 1) if [norm(w) for w in d[:n]] == nb[-n:]), default=0)
    d = d[lead:]
    tail = max((n for n in range(1, min(len(d), len(na)) + 1) if [norm(w) for w in d[-n:]] == na[:n]), default=0)
    return d[:len(d) - tail]


# ------------------------------------------------------------------ audio + Whisper
def load_audio(path):
    import numpy as np
    raw = subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def envelope(x, hop=.02):
    import numpy as np
    n = int(SR * hop)
    k = len(x) // n
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-9
    return [float(v) for v in 20 * np.log10(rms)]


def speech_thr(db):
    """speech threshold relative to this clip's own level (phone audio runs anywhere from -45 to -15 dBFS)"""
    s = sorted(db)
    return max(s[int(len(s) * .9)] - 24, s[int(len(s) * .2)] + 8)


class Ears:
    """faster-whisper on slices of the clips; medium.en only when small.en leaves a doubt"""
    def __init__(self, model):
        self.name, self.models = model, {}

    def model(self, name):
        if name not in self.models:
            self.models[name] = skillenv.whisper(name)
        return self.models[name]

    def hear(self, x, a, b, name=None):
        a, b = max(0.0, a), min(len(x) / SR, b)
        r, _ = self.model(name or self.name).transcribe(x[int(a * SR):int(b * SR)], word_timestamps=True, vad_filter=False,
                                                        beam_size=5, condition_on_previous_text=False)
        return clean([(w.word.strip(), round(a + w.start, 3), round(a + w.end, 3)) for s in r for w in s.words if w.word.strip()])


def check_side(ears, x, isl, seg, words, inside, side):
    """-> (fail message or None, note or None)"""
    a, b = seg['in'], seg['out']
    lm, le, tm, te = edges(words, [h[0] for h in inside])
    missing, extra = (lm, le) if side == 'lead' else (tm, te)
    st = side_status(missing, extra, seg.get('heard_ok', ()))
    if st == 'ok':
        return None, None
    if st == 'misheard':
        return None, f"{side} words {' '.join(missing)!r} heard as {' '.join(extra)!r} (a mishearing: the caption uses the line)"
    for model in (None, 'medium.en'):   # small.en first, medium.en before calling anything missing
        around = ears.hear(x, a - LEAD_PAD, b, model) if side == 'lead' else ears.hear(x, a, b + TRAIL_PAD, model)
        hit = clipped(missing, around, side, a if side == 'lead' else b)
        if hit:
            t = hit[0][1] if side == 'lead' else hit[-1][2]
            s = island_at(isl, t, side)
            said = ' '.join(h[0] for h in around if s and s[0] - .1 <= (h[1] + h[2]) / 2 <= s[1] + .1)
            cut_words = ' '.join(w for w, _, _ in hit)
            if side == 'lead':
                fix = f"start at {max(0, s[0] - .06):.2f} (speech starts {s[0]:.2f}: {said!r})" if s else f"start before {t:.2f}"
                return (f"the in-point {a:.2f} cuts off {cut_words!r} (heard at ~{hit[0][1]:.2f}-{hit[-1][2]:.2f}): "
                        f"{fix}, or take those words out of the line"), None
            fix = f"end at {s[1] + .02:.2f} (speech ends {s[1]:.2f}: {said!r})" if s else f"end after {t:.2f}"
            return (f"the out-point {b:.2f} cuts off {cut_words!r} (heard at ~{hit[0][1]:.2f}-{hit[-1][2]:.2f}): "
                    f"{fix}, or take those words out of the line"), None
        if model is None:   # nothing outside the cut either: does medium.en hear them inside?
            lm2, le2, tm2, te2 = edges(words, [h[0] for h in ears.hear(x, a, b, 'medium.en')])
            if side_status(*((lm2, le2) if side == 'lead' else (tm2, te2)), seg.get('heard_ok', ())) != 'missing':
                return None, f"{side} words {' '.join(missing)!r} only heard by medium.en"
    return (f"the line's {'first' if side == 'lead' else 'last'} words {' '.join(missing)!r} are not in the shot's audio, inside "
            f"or just outside the cut: listen; if they are there add \"heard_ok\": {json.dumps(missing)} to {seg['id']}, "
            f"otherwise fix the line or the cut"), None


def run(proj, edl_path=None, model='small.en', quiet=False):
    """-> True when the EDL passes. Prints a report."""
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    edl_path = edl_path or os.path.join(proj, 'edl.json')
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        src = json.load(fh)
    with open(edl_path, 'rb') as fh:
        blob = fh.read()
    edl = json.loads(blob.decode('utf-8'))
    key = hashlib.sha1(blob + json.dumps(src, sort_keys=True).encode()).hexdigest()
    cache = os.path.join(proj, 'work', 'edl_check.json')
    if os.path.isfile(cache):
        with open(cache, encoding='utf-8') as fh:
            if json.load(fh).get('passed') == key:
                say('EDL check: passed before, EDL unchanged')
                return True
    ears, audio, isl, fails = Ears(model), {}, {}, 0
    for clip in dict.fromkeys(s['clip'] for s in edl):
        audio[clip] = load_audio(src[clip])
        db = envelope(audio[clip])
        isl[clip] = islands(db, thr=speech_thr(db))
    say(f'EDL check ({len(edl)} shots, {model}):')
    for seg in edl:
        x, words = audio[seg['clip']], seg.get('line', '').split()
        if not words:
            say(f"  {seg['id']}  no line: nothing to check (write what is said, it drives the captions)")
            continue
        inside = ears.hear(x, seg['in'], seg['out'])
        msgs, notes = [], []
        for side in ('lead', 'trail'):
            fail, note = check_side(ears, x, isl[seg['clip']], seg, words, inside, side)
            msgs += [fail] if fail else []
            notes += [note] if note else []
        lm, le, tm, te = edges(words, [h[0] for h in inside])
        if le and not lm:
            notes.append(f"heard before the line's first word: {' '.join(le)!r} (false start let in, or Whisper inventing a word)")
        if te and not tm:
            notes.append(f"heard after the line's last word: {' '.join(te)!r}")
        for name, t in (('in', seg['in']), ('out', seg['out'])):
            s = inside_sound(isl[seg['clip']], t, name)
            if s:
                notes.append(f"the {name}-point {t:.2f} sits inside continuous sound {s[0]:.2f}-{s[1]:.2f}: a word may be clipped "
                             f"(nearest silence: {s[0] - .06 if name == 'in' else s[1] + .02:.2f}); fine if you cut between two words on purpose")
        fails += bool(msgs)
        say(f"  {seg['id']}  {'FAIL' if msgs else 'ok  '}  {seg['in']:.2f}-{seg['out']:.2f}  {' '.join(words)}")
        for m in msgs:
            say(f"        !! {m}")
        for n in notes:
            say(f"        .. {n}")
    clip_len = {c: len(x) / SR for c, x in audio.items()}
    drops = gaps(edl, clip_len)
    if drops:
        say('DROPPED by the cut (read these: is any of it part of a line you kept?):')
    for clip, a, b, before, after in drops:
        if not any(s[0] < b and s[1] > a for s in isl[clip]):
            continue   # silence only
        lines = {s['id']: s.get('line', '').split() for s in edl}
        words = [h[0] for h in drop_words(ears.hear(audio[clip], a - 1.0, b + 1.0, 'medium.en'), a, b, isl[clip])]
        said = ' '.join(trim_kept(words, lines.get(before, []), lines.get(after, [])))
        if not said:
            continue   # breaths, room tone
        where = f"between {before} and {after}" if before and after else (f"before {after}" if after else f"after {before}")
        say(f"  {clip} {a:6.2f}-{b:6.2f}  {where:22s} {said}")
    if fails:
        say(f'EDL check FAILED: {fails} shot(s). Fix the EDL (or add "heard_ok" after listening), then run it again.')
        return False
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as fh:
        json.dump({'passed': key}, fh)
    say('EDL check passed.')
    return True


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    edl = skillenv.path_arg(sys.argv[sys.argv.index('--edl') + 1]) if '--edl' in sys.argv else None
    model = sys.argv[sys.argv.index('--model') + 1] if '--model' in sys.argv else 'small.en'
    sys.exit(0 if run(proj, edl, model) else 1)


if __name__ == '__main__':
    main()
