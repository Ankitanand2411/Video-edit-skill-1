#!/usr/bin/env python3
"""/video-edit template: a talking-head reel with every spoken word on screen, punch words tucked behind the head,
and (when the project has storyboard_plan.json) the storyboard's pictures, supers and end card.
It is the finished build of a real reel ("how handwriting helps the brain learn to read": one 87s phone clip + a
5-scene storyboard -> a 68s cool dude reel). Copy it into the project; set the CONTENT block; run it.

Inputs (written by the skill's scripts, nothing to hand-type):
  segments.json (assemble.py)   words.json (align.py)   headpos.json (headpos.py)   storyboard_plan.json (optional,
  storyboard_plan.py)   assets/aroll.mp4  assets/subject/*.webm (cutout.py)  assets/voice.m4a (assemble.py)
  assets/fonts/metrics.json (font metrics: placement and line widths are computed, not eyeballed)
CONTENT to set per reel: LOOK, PUNCH (empty = automatic picks, printed: review them), FIX, IMPACT, and in the cool
girl look SCRIPT_PUNCH (a punch word set in handwriting with a drawn underline) and SPARKLE (None = automatic picks).
MACHINERY (keep): looks, caption lines, behind-head placement, storyboard layer, grades, audio lanes, --range, SAFE_GUIDE.

PY build.py               writes index.html
PY build.py --safe        same + red Instagram safe-zone guide (snapshots only, never render with it)
PY build.py --plan        also prints the caption plan, punch words and storyboard layer
PY build.py --range A B   chunk_<first frame>.html covering [A, B) with no audio (scripts/render.py renders the reel
                          in short sessions to lossless PNG frames, then encodes once)
Also writes work/reel.json (length + the SFX list) for scripts/render.py's audio mix, and work/cutout_plan.json: the
a-roll frames the cutout must cover (only where something sits behind the head; every frame when the look grades the
cutout differently from the room) in pieces of up to 10 s. Run scripts/cutout.py after every build that moves them.
"""
import json
import os
import re
import shutil
import subprocess
import sys

# ================================================================== CONTENT (per reel)
LOOK = 'dude'      # 'dude' (cool dude) | 'girl' (cool girl) | 'bold': config.json defaultLook unless the user asks
PUNCH = [          # (time hint s, spoken word(s), display text, italic): ~1 per shot, the word that carries the line.
    # (1.76, 'handwriting', 'handwriting.', False),       empty list -> automatic picks (printed by --plan): review them
]
FIX = {}           # display fixes for words.json text: {'heard': 'said'} (edl.json lines are the main text source)
IMPACT = None      # a PUNCH display text that gets a soft bass hit (e.g. a year, a number), or None
SCRIPT_PUNCH = set()   # cool girl: PUNCH display texts set in Caveat (handwritten, underline drawn on), e.g. {'ugly handwriting'}
SPARKLE = None     # cool girl: {PUNCH display text: delay s} for the ✦ twinkles; None -> up to 3 words that stay up 1.5s+
END_HOLD = 3.0     # end card length when the storyboard has one

# ================================================================== MACHINERY
SAFE = '--safe' in sys.argv or bool(os.environ.get('SAFE'))
RANGE = tuple(float(x) for x in sys.argv[sys.argv.index('--range') + 1:sys.argv.index('--range') + 3]) if '--range' in sys.argv else None
FF = shutil.which('ffmpeg') or 'ffmpeg'
DUR = float(subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                            'stream=duration', '-of', 'csv=p=0', 'assets/aroll.mp4'],
                           capture_output=True, encoding='utf-8', errors='replace').stdout.strip().split(',')[0])   # a-roll length


def load(f, default=None):
    if not os.path.exists(f):
        return default
    with open(f, encoding='utf-8') as fh:
        return json.load(fh)


SEGS = load('segments.json')
SEG = {s['id']: s for s in SEGS}
ORDER = [s['id'] for s in SEGS]
# cut times = exact first frame of each segment, nudged 2ms early so a tl.set lands ON that frame
T = {k: s['frame'] / 30 - .002 if s['frame'] else 0.0 for k, s in SEG.items()}
END = {sid: (T[ORDER[i + 1]] if i + 1 < len(ORDER) else DUR) for i, sid in enumerate(ORDER)}
CUTS = [T[s] for s in ORDER[1:]]
CLOSE = {s['id'] for s in SEGS if s.get('zoom', 1) > 1}
CREAM, PAPER, YEL = '#F2EFE9', '#F7F4EE', '#FAE67A'
METRICS = load('assets/fonts/metrics.json')
HEADPOS = load('headpos.json', {})
PLAN = load('storyboard_plan.json')

LOOKS = {   # references/looks.md has the why of every value
    'dude': {'room': 'contrast(1.08) saturate(.92) brightness(.86) hue-rotate(-4deg)',      # room moody (storyboard "vibrant": a touch lifted)
             'subject': 'contrast(1.05) saturate(.98) brightness(1.0) hue-rotate(-3deg)',  # the cutout stays lit
             'fx': 'dude', 'cuts': 'push', 'sweeps': True,
             'cap': {'family': 'Montserrat', 'weight': 500, 'font': 'Montserrat-500-normal', 'size': 34, 'case': 'upper', 'track': .32,
                     'gap': .3, 'color': CREAM, 'anim': 'track'},
             'punch': {'family': "'DM Serif Display'", 'weight': 400, 'font': 'DMSerifDisplay-400-normal', 'font_it': 'DMSerifDisplay-400-italic',
                       'lh': 1.12, 'track': -.02, 'size': {'wide': 230, 'close': 210}, 'color': PAPER, 'case': 'lower', 'anim': 'mask', 'italic': None}},
    'girl': {'room': 'sepia(.18) saturate(.9) contrast(.93) brightness(1.05) hue-rotate(-5deg)',
             'subject': 'sepia(.18) saturate(.9) contrast(.93) brightness(1.05) hue-rotate(-5deg)',
             'fx': 'girl', 'cuts': 'punch', 'sweeps': False,
             'cap': {'family': 'Inter', 'weight': 500, 'font': 'Inter-500-normal', 'size': 46, 'case': 'lower', 'track': -.01,
                     'gap': .12, 'color': '#FFF8EF', 'anim': 'rise'},
             'punch': {'family': "'Instrument Serif'", 'weight': 400, 'font': 'InstrumentSerif-400-italic', 'font_it': 'InstrumentSerif-400-italic',
                       'lh': 1.0, 'track': 0, 'size': {'wide': 220, 'close': 200}, 'color': YEL, 'case': 'lower', 'anim': 'rise', 'italic': True}},
    'bold': {'room': 'contrast(1.07) saturate(.9) brightness(.97)', 'subject': 'contrast(1.07) saturate(.9) brightness(.97)',
             'fx': 'bold', 'cuts': 'punch', 'sweeps': False,
             'cap': {'family': "'Inter Tight'", 'weight': 800, 'font': 'InterTight-800-normal', 'size': 62, 'case': 'lower', 'track': -.04,
                     'gap': .14, 'color': '#FFFFFF', 'anim': 'pop'},
             'punch': {'family': "'Inter Tight'", 'weight': 900, 'font': 'InterTight-900-normal', 'font_it': 'InterTight-900-normal',
                       'lh': .9, 'track': -.05, 'size': {'wide': 236, 'close': 220}, 'color': '#FFFFFF', 'case': 'lower', 'anim': 'pop', 'italic': False}},
}
L = LOOKS[LOOK]
CAP, PU = L['cap'], L['punch']
CAP_LH = round(CAP['size'] * 1.25)
SERIF_W = 960          # widest a punch word / caption line may get (35px safe sides + air)
CAPS_MAX = {'wide': 430, 'close': 290}   # the caption line sits in the wall space above the punch word, never above y 228


def seg_at(t):
    return [s for s in ORDER if T[s] <= t + 1e-6][-1]


def shot(sid):
    return 'close' if sid in CLOSE else 'wide'


def at_cut(t):
    return any(abs(t - c) < .01 for c in CUTS)


def text_width(text, size, font, track=0.0, pad=0.0):
    adv = METRICS[font]['adv']
    return size * sum(adv.get(c, .55) + track + pad for c in text)


# ------------------------------------------------------------------ behind-head placement from the font's real metrics
# A block of line-height LH puts the baseline at top + k*S, k = (LH + ascent - descent) / 2. Target: baseline = head
# top + 0.2 * x-height (the hair covers at most the bottom fifth of the lowercase letters). Ascenders reach ~1.05 *
# cap height above the baseline; the caption line must clear them by 24px.
def pmet(it=False):
    m = METRICS[PU['font_it'] if it else PU['font']]
    k = (PU['lh'] + m['ascent'] - m['descent']) / 2
    return k, m['x_height'], m['cap_height']


def head_samples(sid):
    h = HEADPOS.get(sid)
    return h if h else (620, 620, 620) if shot(sid) == 'wide' else (450, 450, 450)   # headpos.py not run: rough defaults


def head_at(sid, t):
    """head top at time t inside shot sid, interpolated between the headpos samples (20% / 50% / 80%)"""
    s, (h1, h2, h3) = SEG[sid], head_samples(sid)
    f = (t - s['frame'] / 30) / (s['frames'] / 30)
    if f <= .5:
        return h1 + (h2 - h1) * max(0, f - .2) / .3
    return h2 + (h3 - h2) * min(1, (f - .5) / .3)


def caps_top(sid):
    k, xh, cap = pmet()
    s0 = PU['size'][shot(sid)]
    return round(max(228, min(CAPS_MAX[shot(sid)], min(head_samples(sid)) + (.2 * xh - 1.05 * cap) * s0 - CAP_LH - 24)))


def behind_head(sid, a, b, text, it):
    """-> (top, size) of a punch word tucked behind the head while it is on screen"""
    k, xh, cap = pmet(it)
    hd = min(head_at(sid, a), head_at(sid, min(b, a + .6)))   # highest the head gets while the word lands
    pad = .04 if PU['anim'] == 'mask' else 0
    fit = SERIF_W / text_width(text, 1, PU['font_it'] if it else PU['font'], PU['track'], pad)
    clear = (hd - caps_top(sid) - CAP_LH - 24) / (1.05 * cap - .2 * xh)
    size = int(min(PU['size'][shot(sid)], fit, clear))
    return round(hd + (.2 * xh - k) * size), size


# ------------------------------------------------------------------ words + punch words
def load_words():
    out = []
    for w in load('words.json'):
        t = w['text'].strip()
        if out and t[:1] == '-' and len(t) > 1 and t[1:2].isalpha():   # "old" "-fashioned," -> "old-fashioned,"
            out[-1]['text'] += t; out[-1]['end'] = w['end']; continue
        core = re.sub(r"[^\w'-]", '', t)
        if core in FIX:
            t = t.replace(core, FIX[core])
        out.append({'text': t, 'start': w['start'], 'end': w['end'], 'seg': w.get('seg') or seg_at(w['start'] + .02)})
    return out


WORDS = load_words()
STOP = set("a an and the of to in on at by for with from as is it its it's be are was were this that these those i we you they he "
           "she my our your their me us them so but or if then than too very just can could would will about into over up down out "
           "not no yes all some any each every while when where what which who how before after because really actually even also "
           "maybe kind lot get got do does did have has had being been know thing things there here like much many more most part "
           "well way still only".split())


def norm(t):
    return re.sub(r"[^\w'-]", '', t).lower()


FILLER = set("started holding everything something anything apparently properly across today found thought wanted going "
             "remember looked looking little really things right being doing making saying getting".split())


def sb_keywords():
    sb = load('storyboard.json') or {}
    text = ' '.join(s.get('script', '') + ' ' + s.get('super', '') + ' ' + ' '.join(s.get('visuals', [])) for s in sb.get('scenes', []))
    return {norm(w).rstrip('s') for w in re.findall(r"[\w'-]+", text) if len(w) > 2}


def auto_punch():
    """no PUNCH given: per shot the word that carries the line, 2 on shots over 3.8s (1.4s apart), none under 1.2s.
    Score: in the storyboard (script / super / visuals) +10, a number +8, ends a phrase +3 (. ? !) or +2 (,), length
    up to +10, -ly adverbs and filler verbs -8. Review the printed picks: the editor's choice beats any heuristic."""
    kw, out = sb_keywords(), []
    for sid in ORDER:
        dur = END[sid] - T[sid]
        if dur < 1.2:
            continue
        cands = []
        for w in WORDS:
            n = norm(w['text'])
            if w['seg'] != sid or n in STOP or len(n) < 3 or (len(n) < 5 and not n.isdigit() and n.rstrip('s') not in kw):
                continue
            end = w['text'].rstrip()[-1:]
            score = (10 * (n.rstrip('s') in kw) + 8 * n.isdigit() + (3 if end in '.?!' else 2 if end == ',' else 0) + min(len(n), 10)
                     - 8 * (n.endswith('ly') or n in FILLER))
            cands.append((score, w))
        picked = []
        for score, w in sorted(cands, key=lambda c: -c[0]):
            if score >= 6 and len(picked) < (2 if dur > 3.8 else 1) and all(abs(w['start'] - q['start']) > 1.4 for q in picked):
                picked.append(w)
        for w in sorted(picked, key=lambda w: w['start']):
            disp = norm(w['text']) + ('.' if w['text'].rstrip()[-1:] == '.' else '')
            out.append((w['start'], norm(w['text']), disp, False))
    return out


def resolve_punch():
    """-> sorted [(word indices, start, display text, italic)], each matched to the nearest spoken occurrence"""
    found = []
    for hint, key, text, it in (PUNCH or auto_punch()):
        toks = key.lower().split()
        cands = [i for i, w in enumerate(WORDS) if norm(w['text']) == toks[0] and abs(w['start'] - hint) < 1.5
                 and all(i + k < len(WORDS) and norm(WORDS[i + k]['text']) == tk for k, tk in enumerate(toks))]
        if not cands:
            sys.exit(f'PUNCH word not found: {key!r} near {hint}s')
        i = min(cands, key=lambda c: abs(WORDS[c]['start'] - hint))
        it = PU['italic'] if PU['italic'] is not None else it
        found.append((list(range(i, i + len(toks))), WORDS[i]['start'], text if PU['case'] != 'upper' else text.upper(), it))
    return sorted(found, key=lambda p: p[1])


PUNCHES = resolve_punch()
PUNCH_IDX = {i for p in PUNCHES for i in p[0]}


def punch_t(text):
    return next((p[1] for p in PUNCHES if p[2] == text), None)


# ------------------------------------------------------------------ caption lines (balanced by measured width)
def cap_text(t):
    t = re.sub(r"[^\w'-]", '', t)
    return t.upper() if CAP['case'] == 'upper' else t.lower()


WEAK = {'a', 'the', 'of', 'to', 'and', 'my', 'our', 'in', 'at', 'by', 'with', 'or'}   # don't end a line on these


def split_lines(txts, maxw):
    """fewest lines no wider than maxw px, then the most even ones (no one-word orphans when avoidable)"""
    n = len(txts)
    width = lambda a, b: sum(text_width(t, CAP['size'], CAP['font'], CAP['track']) for t in txts[a:b]) + (b - a - 1) * CAP['size'] * (2 * CAP['gap'] + .3)
    best = {n: (0, 0, [])}
    for a in range(n - 1, -1, -1):
        opts = [(best[b][0] + 1, max(width(a, b) + 60 * (b < n and txts[b - 1].lower() in WEAK), best[b][1]), [b] + best[b][2])
                for b in range(a + 1, n + 1) if width(a, b) <= maxw or b == a + 1]
        best[a] = min(opts, key=lambda o: (o[0], o[1]))
    out, a = [], 0
    for b in best[0][2]:
        out.append((a, b)); a = b
    return out


def caps_groups():
    """running caption lines: phrases break at cuts, pauses, punctuation and punch words, then split evenly"""
    phrases, cur, prev = [], [], None
    for i, w in enumerate(WORDS):
        if i in PUNCH_IDX:
            if cur:
                phrases.append(cur); cur = []
            prev = w
            continue
        if cur and (cur[-1]['seg'] != w['seg'] or w['start'] - prev['end'] > .45 or prev['text'][-1:] in '.,?!'):
            phrases.append(cur); cur = []
        cur.append(w)
        prev = w
    if cur:
        phrases.append(cur)
    groups = []
    for ph in phrases:
        txts = [cap_text(w['text']) for w in ph]
        for a, b in split_lines(txts, 900):
            groups.append({'sid': ph[a]['seg'], 'words': [(max(w['start'], T[w['seg']] + .02), t) for w, t in zip(ph[a:b], txts[a:b])]})
    for k, g in enumerate(groups):   # a line stays up until the next line of the same shot replaces it
        nxt = groups[k + 1] if k + 1 < len(groups) else None
        g['end'] = nxt['words'][0][0] - .02 if nxt and nxt['sid'] == g['sid'] else END[g['sid']]
    return groups


# ------------------------------------------------------------------ storyboard layer (storyboard_plan.json)
CUTAWAYS = [dict(c) for c in (PLAN or {}).get('cutaways', [])]
SUPERS = [dict(s) for s in (PLAN or {}).get('supers', [])]
ENDC = (PLAN or {}).get('end_card')
END_IN = ENDC['in'] if ENDC else None
REEL_DUR = END_IN + ENDC.get('hold', END_HOLD) if ENDC else DUR
CARD_MAX_W, CARD_BOTTOM, BORDER = 960, 1140, 5   # card + border stays inside 35px sides; ends above the icon column
IMG_SIZE = {}


def snap(t):
    """plan times are rounded to 3 decimals: an edge within 10ms of a cut goes ON the cut (a card hidden at 5.267 with
    the cut at 5.2647 stayed on the first frame of the next shot)"""
    c = min(CUTS, key=lambda c: abs(c - t)) if CUTS else t
    return c if abs(c - t) < .01 else t


for _x in CUTAWAYS + SUPERS:
    _x['a'], _x['b'] = snap(_x['a']), snap(_x['b'])


def img_size(src):
    if src not in IMG_SIZE:
        out = subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', src],
                             capture_output=True, encoding='utf-8').stdout.strip().split(',')
        IMG_SIZE[src] = (int(out[0]), int(out[1]))
    return IMG_SIZE[src]


def fit(src, max_w, max_h):
    w, h = img_size(src)
    s = min(1.0, max_w / w, max_h / h)   # never upscale: a picture shows at its own size or smaller
    return round(w * s), round(h * s)


def display_copy(src, w, h):
    """exact-size copy for 1:1 drawing: one Lanczos downscale; at native size the original itself"""
    if (w, h) == img_size(src):
        return src
    os.makedirs('assets/storyboard/disp', exist_ok=True)
    out = f"assets/storyboard/disp/{os.path.splitext(os.path.basename(src))[0]}_{w}x{h}.png"
    if not os.path.exists(out):
        subprocess.run([FF, '-v', 'error', '-y', '-i', src, '-vf', f'scale={w}:{h}:flags=lanczos+accurate_rnd+full_chroma_int',
                        '-pix_fmt', 'rgb24', out], check=True)
    return out


def backdrop(src):
    """full-frame blurred, darkened copy of the picture behind its card (blurred, so its scale never shows)"""
    os.makedirs('assets/storyboard/disp', exist_ok=True)
    out = f"assets/storyboard/disp/{os.path.splitext(os.path.basename(src))[0]}_bg.jpg"
    if not os.path.exists(out):
        subprocess.run([FF, '-v', 'error', '-y', '-i', src, '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase:flags=bicubic,'
                        'crop=1080:1920,gblur=sigma=46,eq=brightness=-0.13:saturation=1.12', '-q:v', '2', out], check=True)
    return out


def card_html(cid, src, x, y, w, h, z, inner=''):
    return (f'<div id="{cid}" class="card" style="left:{x}px;top:{y}px;width:{w + 2 * BORDER}px;height:{h + 2 * BORDER}px;z-index:{z}">'
            f'<img src="{display_copy(src, w, h)}" width="{w}" height="{h}" alt="">{inner}</div>')


for _c in CUTAWAYS:   # a punch word gets ~1s on screen before a cutaway covers it (keep >= 2s of cutaway)
    for _p in PUNCHES:
        if (_c['a'] - 1.0 < _p[1] < _c['a'] and _c['b'] - (_p[1] + 1.0) >= 2.0
                and seg_at(_p[1]) == seg_at(_c['a'] + .02)):   # a word in the previous shot ends at the cut anyway
            _c['a'] = round(_p[1] + 1.0, 3)
for _c in CUTAWAYS:   # card rectangles, integer pixels, under the caption line of the shot the cutaway opens on
    if _c['kind'] == 'card':
        _top = caps_top(seg_at(_c['a'] + .02)) + CAP_LH + 28
        _w, _h = fit(_c['image'], CARD_MAX_W, CARD_BOTTOM - _top)
        _c.update(w=_w, h=_h, x=(1080 - _w - 2 * BORDER) // 2, y=_top)


def window_of(t):
    return next((c for c in CUTAWAYS if c['a'] - .01 <= t < c['b']), None)


def rise_in(sel, t, dist=46):
    """card entrance: fade + rise, then the transform is cleared so the resting picture sits on exact pixels"""
    return [f"tl.fromTo('{sel}',{{autoAlpha:0,y:{dist},scale:.965}},{{autoAlpha:1,y:0,scale:1,duration:.55,ease:'power3.out',immediateRender:false}},{t:.3f});",
            f"tl.set('{sel}',{{clearProps:'transform'}},{t + .58:.3f});"]


def hide(sel, b, cut=False, dur=.2):
    if cut:
        return [f"tl.set('{sel}',{{autoAlpha:0}},{b:.3f});"]
    return [f"tl.to('{sel}',{{autoAlpha:0,duration:{dur}}},{b - dur:.3f});", f"tl.set('{sel}',{{autoAlpha:0}},{b:.3f});"]


def punch_div(pid, text, it, top, size, cls='pw', color=None, z=None):
    style = f'top:{top}px;font-size:{size}px' + (f';color:{color}' if color else '') + (f';z-index:{z}' if z else '')
    if PU['anim'] == 'mask':
        inner = ''.join(f'<span class="mk"><span class="ch">{"&nbsp;" if c == " " else c}</span></span>' for c in text)
    else:
        inner = text
    return f'<div id="{pid}" class="{cls}{" it" if it else ""}" style="{style}">{inner}</div>'


def punch_in(sel, a):
    if PU['anim'] == 'mask':   # letters rise from a mask, the word settles from a soft blur
        return [f"gsap.set('{sel}',{{autoAlpha:0}});", f"tl.set('{sel}',{{autoAlpha:1}},{a:.3f});",
                f"tl.fromTo('{sel} .ch',{{yPercent:115}},{{yPercent:0,duration:.6,ease:'expo.out',stagger:.028,immediateRender:false}},{a:.3f});",
                f"tl.fromTo('{sel}',{{scale:1.06,filter:'blur(6px)'}},{{scale:1,filter:'blur(0px)',duration:.4,ease:'power3.out',immediateRender:false}},{a:.3f});"]
    if PU['anim'] == 'rise':
        return [f"gsap.set('{sel}',{{autoAlpha:0}});",
                f"tl.fromTo('{sel}',{{autoAlpha:0,y:22,scale:.92}},{{autoAlpha:1,y:0,scale:1,duration:.4,ease:'power2.out',immediateRender:false}},{a:.3f});"]
    return [f"gsap.set('{sel}',{{autoAlpha:0}});",   # pop
            f"tl.fromTo('{sel}',{{autoAlpha:0,scale:1.22,filter:'blur(22px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',duration:.2,ease:'power3.out',immediateRender:false}},{a:.3f});"]


def word_in(sel, t):
    if CAP['anim'] == 'track':   # "tracking in" with scaleX (letterSpacing tweens stutter under frame capture)
        return f"tl.fromTo('{sel}',{{autoAlpha:0,scaleX:1.45,filter:'blur(8px)'}},{{autoAlpha:1,scaleX:1,filter:'blur(0px)',duration:.45,ease:'power3.out',immediateRender:false}},{t:.3f});"
    if CAP['anim'] == 'rise':
        return f"tl.fromTo('{sel}',{{autoAlpha:0,y:14}},{{autoAlpha:1,y:0,duration:.26,ease:'power2.out',immediateRender:false}},{t:.3f});"
    return f"tl.fromTo('{sel}',{{autoAlpha:0,scale:1.22,filter:'blur(16px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',duration:.2,ease:'power3.out',immediateRender:false}},{t:.3f});"


def cutaways():
    html, tw = [], []
    for c in CUTAWAYS:
        cid, a, b = c['id'], c['a'], c['b']
        if c['kind'] == 'card':
            html.append(f'<div id="{cid}-bg" class="cbg" style="z-index:10"><img src="{backdrop(c["image"])}" alt=""></div>')
            html.append(card_html(f'{cid}-card', c['image'], c['x'], c['y'], c['w'], c['h'], 11))
            tw.append(f"gsap.set(['#{cid}-bg','#{cid}-card'],{{autoAlpha:0}});")
            tw += ([f"tl.set('#{cid}-bg',{{autoAlpha:1}},{a:.3f});"] if at_cut(a) else
                   [f"tl.fromTo('#{cid}-bg',{{autoAlpha:0}},{{autoAlpha:1,duration:.22,ease:'power1.out',immediateRender:false}},{a:.3f});"])
            tw += rise_in(f'#{cid}-card', a + .04) + hide(f'#{cid}-bg,#{cid}-card', b, at_cut(b))
        else:   # split: two cards stacked, a label on each, an italic "vs." between them
            sizes = [fit(s, 760, 520) for s in c['images']]
            x, y1 = (1080 - sizes[0][0] - 2 * BORDER) // 2, 236
            y2 = y1 + sizes[0][1] + 2 * BORDER + 150
            k, xh, cap = pmet(True)
            vs_size = 128
            vs_top = round(y1 + sizes[0][1] + 2 * BORDER + 75 - (k - xh / 2) * vs_size)   # x-height centred in the gap
            html.append(f'<div id="{cid}-bg" class="cbg split" style="z-index:13"></div>')
            for n, (src, (w, h), y, lab) in enumerate(zip(c['images'], sizes, (y1, y2), c['labels'])):
                html.append(card_html(f'{cid}-c{n}', src, x, y, w, h, 14, inner=f'<div id="{cid}-l{n}" class="pill">{lab}</div>'))
            html.append(punch_div(f'{cid}-vs', 'vs.', True, vs_top, vs_size, 'pw front', YEL, 14))
            tw += [f"gsap.set(['#{cid}-bg','#{cid}-c0','#{cid}-c1','#{cid}-l0','#{cid}-l1'],{{autoAlpha:0}});",
                   f"tl.fromTo('#{cid}-bg',{{autoAlpha:0}},{{autoAlpha:1,duration:.22,ease:'power1.out',immediateRender:false}},{a:.3f});"]
            tw += rise_in(f'#{cid}-c0', a + .04) + rise_in(f'#{cid}-c1', c['bottom_t'])
            tw += [f"tl.fromTo('#{cid}-l{n}',{{autoAlpha:0,scaleX:1.45,filter:'blur(8px)'}},{{autoAlpha:1,scaleX:1,filter:'blur(0px)',"
                   f"duration:.45,ease:'power3.out',immediateRender:false}},{t:.3f});" for n, t in enumerate(c['label_t'])]
            tw += punch_in(f'#{cid}-vs', c['vs_t']) + hide(f'#{cid}-bg,#{cid}-c0,#{cid}-c1,#{cid}-vs', b, at_cut(b))
    return html, tw


ARROW = ('<svg width="34" height="14" viewBox="0 0 34 14"><path d="M1 7h30M25 1.5 31.5 7 25 12.5" fill="none" stroke="currentColor" '
         'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')   # the fonts carry no arrow glyph


def supers():
    html, tw = [], []
    for s in SUPERS:
        sid_, a, b = s['id'], s['a'], s['b']
        if s['kind'] == 'steps':   # the whole progression shows dimmed; each step lights up (accent) as it is said
            parts = []
            for k, (_, word) in enumerate(s['steps']):
                if k:
                    parts.append(f'<span id="{sid_}-a{k}" class="ar">{ARROW}</span>')
                parts.append(f'<span id="{sid_}-s{k}" class="st">{word}</span>')
            html.append(f'<div class="lt"><div id="{sid_}" class="plate">{"".join(parts)}</div></div>')
            tw += [f"gsap.set('#{sid_}',{{autoAlpha:0}});", f"gsap.set('#{sid_} .st, #{sid_} .ar',{{autoAlpha:.3}});",
                   f"tl.fromTo('#{sid_}',{{autoAlpha:0,y:16}},{{autoAlpha:1,y:0,duration:.35,ease:'power3.out',immediateRender:false}},{a + .15:.3f});"]
            for k, (t, _) in enumerate(s['steps']):
                if k:
                    tw += [f"tl.to('#{sid_}-a{k}',{{autoAlpha:1,duration:.25}},{t - .1:.3f});",
                           f"tl.set('#{sid_}-s{k - 1}',{{color:'{CREAM}'}},{t - .04:.3f});"]
                tw += [f"tl.set('#{sid_}-s{k}',{{color:'{YEL}'}},{t - .04:.3f});",
                       f"tl.fromTo('#{sid_}-s{k}',{{autoAlpha:.3,scaleX:1.3,filter:'blur(6px)'}},{{autoAlpha:1,scaleX:1,filter:'blur(0px)',"
                       f"duration:.4,ease:'power3.out',immediateRender:false}},{t - .04:.3f});"]
        else:
            words = s['text'].split()
            spans = ''.join(f'<span id="{sid_}-w{k}" class="st{" y" if k >= len(words) - s.get("yellow_last", 0) else ""}">{w}</span>'
                            for k, w in enumerate(words))
            html.append(f'<div class="lt"><div id="{sid_}" class="plate words">{spans}</div></div>')
            tw += [f"gsap.set('#{sid_}',{{autoAlpha:0}});", f"gsap.set('#{sid_} .st',{{autoAlpha:0}});",
                   f"tl.fromTo('#{sid_}',{{autoAlpha:0}},{{autoAlpha:1,duration:.25,immediateRender:false}},{a:.3f});",
                   f"tl.fromTo('#{sid_} .st',{{autoAlpha:0,scaleX:1.45,filter:'blur(8px)'}},{{autoAlpha:1,scaleX:1,filter:'blur(0px)',"
                   f"duration:.45,ease:'power3.out',stagger:.07,immediateRender:false}},{a + .05:.3f});"]
        tw += hide(f'#{sid_}', b, at_cut(b))
    return html, tw


def end_card():
    if not ENDC:
        return [], []
    inner, tw = [], ["gsap.set('#endc',{autoAlpha:0});",
                     f"tl.fromTo('#endc',{{autoAlpha:0}},{{autoAlpha:1,duration:.3,ease:'power1.out',immediateRender:false}},{END_IN:.3f});"]
    top = 420
    if ENDC.get('image'):
        w, h = fit(ENDC['image'], CARD_MAX_W, 640)
        x, y = (1080 - w - 2 * BORDER) // 2, 290
        inner += [f'<img class="ebg" src="{backdrop(ENDC["image"])}" alt="">', card_html('end-card', ENDC['image'], x, y, w, h, 2)]
        tw += ["gsap.set('#end-card',{autoAlpha:0});"] + rise_in('#end-card', END_IN + .06)
        top = y + h + 2 * BORDER + 20
    for k, line in enumerate(ENDC.get('lines', [])):
        it = k == len(ENDC['lines']) - 1 and len(ENDC['lines']) > 1   # the last line: italic, accent colour
        size = int(min(150, SERIF_W / text_width(line, 1, PU['font_it'] if it else PU['font'], PU['track'], .04)))
        inner.append(punch_div(f'end-l{k}', line, it or bool(PU['italic']), top, size, 'pw front',
                               YEL if it else ('#FFF8EF' if L['fx'] == 'girl' else None)))   # girl: only the last line yellow
        tw += punch_in(f'#end-l{k}', END_IN + .55 + .6 * k)
        top += round(size * 1.12)
    return [f'<div id="endc" style="z-index:20">{"".join(inner)}</div>'], tw


# ------------------------------------------------------------------ cool girl extras: handwritten punch word, sparkles
SCRIPT_FONT, SCRIPT_LH = 'Caveat-600-normal', 1.0
POS = {}   # punch display text -> (top, size, front, font, a, b), filled by core()


def script_k():
    m = METRICS[SCRIPT_FONT]
    return (SCRIPT_LH + m['ascent'] - m['descent']) / 2, m['x_height'], m['cap_height']


def script_behind_head(sid, a, b, text):
    """behind_head() with Caveat's own metrics"""
    k, xh, cap = script_k()
    hd = min(head_at(sid, a), head_at(sid, min(b, a + .6)))
    fit = SERIF_W / text_width(text, 1, SCRIPT_FONT, 0, .02)
    clear = (hd - caps_top(sid) - CAP_LH - 24) / (1.05 * cap - .2 * xh)
    size = int(min(200, fit, clear))
    return round(hd + (.2 * xh - k) * size), size


def script_div(pid, text, top, size):
    k, xh, cap = script_k()
    w = round(text_width(text, size, SCRIPT_FONT, 0, .02)) + 30
    h = round(size * .2)
    uy = round(k * size + size * .07)   # just under the baseline: the head hides its middle, both ends stay visible
    path = (f'M6,{h * .62:.0f} C{w * .22:.0f},{h * .2:.0f} {w * .46:.0f},{h * .9:.0f} {w * .7:.0f},{h * .45:.0f} '
            f'S{w - 34:.0f},{h * .28:.0f} {w - 6:.0f},{h * .5:.0f}')
    chars = ''.join(f'<span class="ch">{"&nbsp;" if c == " " else c}</span>' for c in text)
    svg = (f'<svg class="ul" width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="top:{uy}px;margin-left:{-w // 2}px">'
           f'<path d="{path}" pathLength="1" fill="none" stroke="{YEL}" stroke-width="{max(5, round(size * .045))}" '
           f'stroke-linecap="round"/></svg>')
    return f'<div id="{pid}" class="pw script" style="top:{top}px;font-size:{size}px">{chars}{svg}</div>'


def script_in(sel, a, n):
    """written on: letters appear left to right, then the underline is drawn"""
    return [f"gsap.set('{sel}',{{autoAlpha:0}});", f"gsap.set('{sel} .ch',{{autoAlpha:0}});", f"gsap.set('{sel} path',{{strokeDashoffset:1}});",
            f"tl.set('{sel}',{{autoAlpha:1}},{a:.3f});",
            f"tl.fromTo('{sel} .ch',{{autoAlpha:0,y:10,filter:'blur(4px)'}},{{autoAlpha:1,y:0,filter:'blur(0px)',duration:.2,ease:'power2.out',"
            f"stagger:.032,immediateRender:false}},{a:.3f});",
            f"tl.fromTo('{sel} path',{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:.45,ease:'power2.inOut',immediateRender:false}},{a + n * .032:.3f});"]


def sparkle_picks():
    """SPARKLE as set, or up to 3 words that stay up 1.5s+ (the handwritten ones first), 10s+ apart"""
    if SPARKLE is not None:
        return dict(SPARKLE)
    up = sorted(((t, p) for t, p in POS.items() if p[5] - p[4] >= 1.5), key=lambda x: (x[0] not in SCRIPT_PUNCH, -(x[1][5] - x[1][4])))
    picks = {}
    for t, p in up:
        if len(picks) < 3 and all(abs(p[4] - POS[q][4]) >= 10 for q in picks):
            picks[t] = .1 if t in SCRIPT_PUNCH else .05
    return picks


def sparkles():
    """two or three ✦ twinkle beside the chosen italic words (behind the head with them, or in front over a card)"""
    back, front, tw = [], [], []
    n = 0
    for text, delay in sparkle_picks().items():
        if text not in POS:
            continue
        top, size, is_front, font, a, b = POS[text]
        w = text_width(text, size, font, PU['track'] if font != SCRIPT_FONT else 0)
        spots = [(540 + w / 2 + 6, top + size * .02, 58), (540 - w / 2 - 54, top + size * .5, 38), (540 + w / 2 - 30, top - 34, 28)]
        for k, (x, y, sz) in enumerate(spots):
            x = max(45, min(1080 - 45 - sz, x))
            y = max(232, y)
            sid_ = f'sp{n}'
            n += 1
            (front if is_front else back).append(f'<div id="{sid_}" class="spark" style="left:{x:.0f}px;top:{y:.0f}px;font-size:{sz}px;'
                                                 f'z-index:{12 if is_front else 3}">&#10022;</div>')
            t = a + delay + .12 + k * .14
            tw += [f"gsap.set('#{sid_}',{{autoAlpha:0,scale:0}});",
                   f"tl.fromTo('#{sid_}',{{autoAlpha:0,scale:0,rotation:-40}},{{autoAlpha:1,scale:1,rotation:0,duration:.32,ease:'back.out(2.5)',immediateRender:false}},{t:.3f});",
                   f"tl.to('#{sid_}',{{scale:.68,duration:.38,yoyo:true,repeat:1,ease:'sine.inOut'}},{t + .32:.3f});"]
            end = min(b, REEL_DUR) if b < DUR - .01 else (END_IN if ENDC else DUR)
            tw += [f"tl.to('#{sid_}',{{autoAlpha:0,duration:.14}},{end - .14:.3f});", f"tl.set('#{sid_}',{{autoAlpha:0}},{end:.3f});"]
    return back, front, tw


# ------------------------------------------------------------------ captions + punch words
def core():
    caps_html, back_html, front_html, tw = [], [], [], []
    for g, grp in enumerate(caps_groups()):
        a, b, top = grp['words'][0][0], grp['end'], caps_top(grp['sid'])
        spans = ''.join(f'<span id="c{g}-{k}" class="tw">{w}</span>' for k, (_, w) in enumerate(grp['words']))
        caps_html.append(f'<div id="c{g}" class="cap" style="top:{top}px">{spans}</div>')
        for k, (t, _) in enumerate(grp['words']):
            tw += [f"gsap.set('#c{g}-{k}',{{autoAlpha:0}});", word_in(f'#c{g}-{k}', max(a, t - .04))]
        if b < END[grp['sid']] - .01:
            tw.append(f"tl.to('#c{g}',{{autoAlpha:0,filter:'blur(6px)',duration:.14}},{b - .14:.3f});")
        tw.append(f"tl.set('#c{g}',{{autoAlpha:0}},{b:.3f});")
    for k, (idx, t, text, it) in enumerate(PUNCHES):
        sid = WORDS[idx[0]]['seg']
        a = max(t - .04, T[sid] + .02)
        win = window_of(a)
        if win and win['kind'] == 'split':   # the split screen's own labels say these words
            continue
        nxt = PUNCHES[k + 1][1] - .04 if k + 1 < len(PUNCHES) else DUR + 1   # the last word holds to the end
        b = min(END[sid], nxt - .02, a + 1.9) if END[sid] < DUR - .01 else min(nxt - .02, DUR)
        if win:   # over a cutaway: the word sits in front, under the card
            b = min(b, win['b'])
            size = int(min(150, SERIF_W / text_width(text, 1, PU['font_it'] if it else PU['font'], PU['track'], .04)))
            top = win['y'] + win['h'] + 2 * BORDER + 16
            front_html.append(punch_div(f's{k}', text, it, top, size, 'pw front'))
            POS[text] = (top, size, True, PU['font_it'] if it else PU['font'], a, b)
            tw += punch_in(f'#s{k}', a)
        elif text in SCRIPT_PUNCH:   # handwritten word behind the head, underline drawn under it
            top, size = script_behind_head(sid, a, b, text)
            back_html.append(script_div(f's{k}', text, top, size))
            POS[text] = (top, size, False, SCRIPT_FONT, a, b)
            tw += script_in(f'#s{k}', a, len(text))
        else:
            top, size = behind_head(sid, a, b, text, it)
            back_html.append(punch_div(f's{k}', text, it, top, size))
            POS[text] = (top, size, False, PU['font_it'] if it else PU['font'], a, b)
            tw += punch_in(f'#s{k}', a)
        if b >= DUR - .01:
            continue
        if b - a < .8 or at_cut(b) or (win and abs(b - win['b']) < .01):   # short, or ends on a cut: hard out
            tw.append(f"tl.set('#s{k}',{{autoAlpha:0}},{b:.3f});")
        else:
            tw += [f"tl.to('#s{k}',{{autoAlpha:0,y:-14,filter:'blur(10px)',duration:.18,ease:'power2.in'}},{b - .18:.3f});",
                   f"tl.set('#s{k}',{{autoAlpha:0,y:0}},{b:.3f});"]
    return caps_html, back_html, front_html, tw


# ------------------------------------------------------------------ grade, motion, sound
SCENE_STARTS = [s['start'] for s in (PLAN or {}).get('scenes', [])[1:]]


def fx():
    html, tw = [], []
    for k, t in enumerate(([.15] + [s + .1 for s in SCENE_STARTS]) if L['sweeps'] else []):   # one soft light sweep per new part
        html.append(f'<div id="sweep{k}" class="fx sweep"></div>')
        tw += [f"gsap.set('#sweep{k}',{{autoAlpha:0}});", f"tl.set('#sweep{k}',{{autoAlpha:1}},{t:.3f});",
               f"tl.fromTo('#sweep{k}',{{backgroundPosition:'130% 0%'}},{{backgroundPosition:'-30% 0%',duration:1.3,ease:'power2.inOut',immediateRender:false}},{t:.3f});",
               f"tl.set('#sweep{k}',{{autoAlpha:0}},{t + 1.35:.3f});"]
    return html, tw


def grades():
    tw = [f"gsap.set('.g',{{filter:'{L['room']}'}});",   # the cutout pieces get theirs in build() (.cut)
          "tl.fromTo('#stage',{filter:'blur(18px) brightness(1.35)'},{filter:'blur(0px) brightness(1)',duration:.45,ease:'power3.out',immediateRender:false},0);",
          "tl.set('#stage',{filter:'none'},.47);"]   # quick blur-to-focus into the reel
    for sid in ORDER:
        a, b = T[sid], END[sid]
        if L['cuts'] == 'push':   # slow push-in across every shot
            tw.append(f"tl.fromTo('#stage',{{scale:1}},{{scale:1.04,duration:{b - a - .005:.3f},ease:'none',immediateRender:false}},{a:.3f});")
        elif a > 0:               # a punch on every cut
            tw.append(f"tl.fromTo('#stage',{{scale:1.05}},{{scale:1,duration:.32,ease:'power2.out',immediateRender:false}},{a:.3f});")
    return tw


def sfx_list():
    out, used = [('whoosh-short', .05, .22)], [.05]
    for t in SCENE_STARTS + [c['a'] for c in CUTAWAYS] + ([END_IN] if ENDC else []):
        if all(abs(t - u) > .8 for u in used):
            out.append(('whoosh-short', t, .2)); used.append(t)
    out += [('pop', c['bottom_t'], .14) for c in CUTAWAYS if c['kind'] == 'split']
    out += [('sparkle', punch_t(t) + .3, .12) for t in sorted(SCRIPT_PUNCH) if punch_t(t) is not None]   # under the handwriting
    if IMPACT and punch_t(IMPACT) is not None:
        out.append(('impact-bass-1', punch_t(IMPACT) - .03, .16))
    return out


SFX = sfx_list()
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'sparkle': 1.8, 'click': .3, 'click-soft': .37, 'impact-bass-1': 2.1}
SFX_GAIN = 0.75   # sounds sit 25% under the original levels: subtle, never louder than the voice


def audio():
    out, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(SFX, key=lambda x: x[1])):
        d = min(SFX_LEN[name], REEL_DUR - t)
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0); lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


FX_LAYERS = {
    'dude': ('<div id="ktone" class="fx"></div><div id="kvig" class="fx"></div><div id="kgrad" class="fx"></div>',
             '#ktone{z-index:7;background:linear-gradient(180deg,rgba(15,45,70,.26),rgba(10,20,35,.26));mix-blend-mode:soft-light}'
             '#kvig{z-index:7;background:radial-gradient(80% 55% at 50% 44%,rgba(0,0,0,0) 40%,rgba(0,0,0,.46) 100%)}'
             '#kgrad{z-index:7;background:linear-gradient(180deg,rgba(0,0,0,0) 66%,rgba(0,0,0,.38) 100%)}'),
    'girl': ('<div id="gwarm" class="fx"></div><div id="gvig" class="fx"></div><div id="ggrad" class="fx"></div>',
             '#gwarm{z-index:7;background:linear-gradient(180deg,rgba(255,226,200,.10),rgba(255,196,170,.16));mix-blend-mode:soft-light}'
             '#gvig{z-index:7;background:radial-gradient(120% 70% at 50% 45%,rgba(255,255,255,0) 52%,rgba(60,35,25,.34) 100%)}'
             '#ggrad{z-index:7;background:linear-gradient(180deg,rgba(60,35,25,.30) 0%,rgba(60,35,25,0) 30%,rgba(60,35,25,0) 66%,rgba(40,24,18,.45) 100%)}'),
    'bold': ('<div id="dtone" class="fx"></div><div id="dvig" class="fx"></div><div id="dgrad" class="fx"></div>',
             '#dtone{z-index:7;background:linear-gradient(180deg,rgba(20,55,75,.16),rgba(60,40,20,.08));mix-blend-mode:soft-light}'
             '#dvig{z-index:7;background:radial-gradient(95% 62% at 50% 46%,rgba(0,0,0,0) 55%,rgba(0,0,0,.42) 100%)}'
             '#dgrad{z-index:7;background:linear-gradient(180deg,rgba(0,0,0,.34) 0%,rgba(0,0,0,0) 22%,rgba(0,0,0,0) 58%,rgba(0,0,0,.30) 100%)}'),
}

CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0;transform-origin:50% 45%}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:0}}
#cutwrap{{position:absolute;inset:0;z-index:4}}
.fx{{position:absolute;inset:0;pointer-events:none}}
{FX_LAYERS[L['fx']][1]}
.sweep{{z-index:7;mix-blend-mode:screen;background:linear-gradient(105deg,rgba(255,240,220,0) 38%,rgba(255,240,220,.22) 50%,rgba(255,240,220,0) 62%);
  background-size:260% 100%;background-repeat:no-repeat}}

/* running captions, above the cutaway backdrops */
.cap{{position:absolute;left:60px;right:60px;z-index:12;text-align:center;color:{CAP['color']};font-family:{CAP['family']};font-weight:{CAP['weight']};
  font-size:{CAP['size']}px;line-height:1.25;text-shadow:0 2px 14px rgba(0,0,0,.7);white-space:nowrap}}
.cap .tw{{display:inline-block;letter-spacing:{CAP['track']}em;margin:0 {CAP['gap']}em;transform-origin:50% 50%}}

/* punch words: behind the head (inside #stage, under the cutout), or .front over a cutaway / on the end card */
.pw{{position:absolute;left:0;right:0;z-index:3;text-align:center;color:{PU['color']};font-family:{PU['family']};font-weight:{PU['weight']};
  line-height:{PU['lh']};letter-spacing:{PU['track']}em;white-space:nowrap;text-shadow:0 12px 40px rgba(0,0,0,.45);transform-origin:50% 60%}}
.pw.front{{z-index:12}}
.pw.it{{font-style:italic}}
.pw .mk{{display:inline-block;overflow:hidden;padding:0 .02em .14em;margin-bottom:-.14em;vertical-align:bottom}}
.pw .ch{{display:inline-block}}

/* storyboard pictures: drawn 1:1 (exact-size display copies), no tilt, no scale at rest */
.cbg{{position:absolute;inset:0;overflow:hidden;background:#0d1015}}
.cbg img,.ebg{{position:absolute;inset:0;width:1080px;height:1920px;display:block}}
.cbg.split{{background:radial-gradient(120% 80% at 50% 42%,#26303c 0%,#141a22 55%,#0b0e13 100%)}}
.card{{position:absolute;border:{BORDER}px solid {PAPER};border-radius:22px;overflow:hidden;background:#111;
  box-shadow:0 34px 90px rgba(0,0,0,.55),0 8px 22px rgba(0,0,0,.3)}}
.card img{{display:block}}
.pill{{position:absolute;left:18px;top:18px;padding:11px 18px 10px 22px;border-radius:999px;background:rgba(10,13,18,.74);
  color:{CREAM};font:500 24px Montserrat;letter-spacing:.28em;white-space:nowrap;transform-origin:0 50%}}
#endc{{position:absolute;inset:0;overflow:hidden;background:#0d1015}}
#endc .pw{{z-index:3}}

/* storyboard SUPER lines: lower-third plates under the chin, clear of the icon column */
.lt{{position:absolute;left:0;right:0;top:1398px;z-index:12;text-align:center}}
.plate{{display:inline-block;padding:16px 26px 15px 32px;border-radius:999px;background:rgba(10,13,18,.62);
  border:1px solid rgba(247,244,238,.16);color:{CREAM};font:500 26px Montserrat;white-space:nowrap;box-shadow:0 12px 34px rgba(0,0,0,.35)}}
.plate .st{{display:inline-block;letter-spacing:.24em;transform-origin:50% 50%}}
.plate.words .st{{margin:0 .22em}}
.plate .st.y{{color:{YEL}}}
.plate .ar{{display:inline-block;margin:0 .55em 0 .32em;color:{CREAM};vertical-align:2px}}
.plate .ar svg{{display:block}}
'''

GIRL_CSS = f'''
/* cool girl: warm room behind the pictures, serif italic plates and labels, sparkles, handwritten punch word */
.cbg{{background:#1b1411}}
.cbg.split{{background:radial-gradient(120% 80% at 50% 42%,#4a362c 0%,#261b16 55%,#150f0c 100%)}}
#endc{{background:#1b1411}}
.plate{{background:rgba(48,30,22,.52);border:1px solid rgba(255,248,239,.22);color:#FFF8EF;font:italic 400 50px 'Instrument Serif';
  padding:8px 34px 12px 34px;text-transform:lowercase;box-shadow:0 12px 34px rgba(40,20,10,.35)}}
.plate .st{{letter-spacing:0}}
.plate.words .st{{margin:0 .12em}}
.plate .ar{{vertical-align:8px}}
.pill{{font:italic 400 40px 'Instrument Serif';letter-spacing:0;text-transform:lowercase;padding:4px 22px 9px 22px;
  background:rgba(40,26,20,.72);color:#FFF8EF}}
.spark{{position:absolute;color:{YEL};line-height:1;text-shadow:0 0 18px rgba(250,230,122,.55);transform-origin:50% 50%}}
.pw.script{{font-family:'Caveat';font-weight:600;font-style:normal;line-height:1;letter-spacing:.02em;color:#FFF8EF;
  text-shadow:0 10px 34px rgba(60,30,20,.5)}}
.pw.script .ch{{display:inline-block}}
.pw.script .ul{{position:absolute;left:50%;overflow:visible;stroke-dasharray:1;filter:drop-shadow(0 4px 10px rgba(60,30,20,.4))}}
''' if L['fx'] == 'girl' else ''
CSS += GIRL_CSS

# PY build.py --safe: draws the Instagram safe zone (red = UI covers it) for snapshot checks, never for renders
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


# ------------------------------------------------------------------ cutout: only where something sits behind the head
# Everything behind the head lives in #stage between the a-roll and the cutout (back_html). Anywhere else the cutout
# shows the same pixels as the a-roll under it (same grade in the girl and bold looks), so it is not needed there:
# it costs ~45% of every rendered frame (816 vs 447 ms, 1 browser) and 1 s of CPU per frame to cut out.
CUT_MARGIN, CUT_MERGE, CUT_PIECE = 3, 8, 300    # frames kept on each side / gaps closed / longest piece
FPS = 30
FRAMES = round(DUR * FPS)
NOT_ZERO = re.compile(r'(?:autoAlpha|opacity):(?!0(?![.\d]))[\d.]+')
ZERO = re.compile(r'(?:autoAlpha|opacity):0(?![.\d])')


def html_ids(html):
    return [i for h in html for i in re.findall(r'<\w+[^>]*\bid="([^"]+)"', h)]


def hides(code):
    """True when these tween vars leave the element invisible"""
    return bool(ZERO.search(code)) and not NOT_ZERO.search(code)


def shown_windows(ids, tweens, end):
    """{id: (from s, to s)}: when each element can be on screen, read from its tweens. Hidden by a gsap.set -> from
    its first timeline tween, else from 0; its last tween hides it -> until that tween ends, else to `end`. Never
    less than the truth: an element shown twice gets one window over both."""
    want, hidden0, seen = set(ids), set(), {}
    for code in tweens:
        m = re.match(r"\s*(tl|gsap)\.(set|to|from|fromTo)\('([^']*)'", code)
        if not m:
            continue
        for i in set(re.findall(r'#([\w-]+)', m.group(3))) & want:
            if m.group(1) == 'gsap':
                if hides(code):
                    hidden0.add(i)
                continue
            at = re.search(r',\s*(-?[\d.]+)\s*\)\s*;?\s*$', code)
            dur = re.findall(r'duration:([\d.]+)', code)
            rep = re.search(r'repeat:(\d+)', code)
            t = float(at.group(1)) if at else 0.0
            span = (float(dur[-1]) if dur else 0.0) * (1 + (int(rep.group(1)) if rep else 0))
            final = code.split('},{', 1)[1] if m.group(2) == 'fromTo' and '},{' in code else code
            seen.setdefault(i, []).append((t, t + span, hides(final)))
    out = {}
    for i in ids:
        tw = sorted(seen.get(i, []), key=lambda x: (x[1], x[0]))
        if not tw:
            if i not in hidden0:
                out[i] = (0.0, end)
            continue
        out[i] = (min(x[0] for x in tw) if i in hidden0 else 0.0, tw[-1][1] if tw[-1][2] else end)
    return out


def cut_pieces(windows, frames, margin=CUT_MARGIN, merge=CUT_MERGE, piece=CUT_PIECE, fps=FPS):
    """-> [(first frame, end frame)]: the a-roll frames the cutout must cover, gaps under `merge` closed, split into
    pieces of at most `piece` frames (pieces are cut out side by side, and a rebuild only redoes the pieces it moves)"""
    spans = sorted((max(0, int(a * fps) - margin), min(frames, -int(-b * fps // 1) + margin)) for a, b in windows)
    merged = []
    for a, b in spans:
        if b <= a:
            continue
        if merged and a - merged[-1][1] <= merge:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        n = -(-(b - a) // piece)
        step = -(-(b - a) // n)
        out += [(x, min(b, x + step)) for x in range(a, b, step)]
    return out


def piece_file(a, b):
    return f'assets/subject/{a:05d}-{b:05d}.webm'


def floor6(x):
    return int(x * 1e6) / 1e6


def media_start(frame, fps=FPS):
    """data-media-start for a video starting at this frame of its file: a quarter frame early. HyperFrames extracts
    with `ffmpeg -ss <media start>`, which drops a frame that starts even a hair before it ("17.967" loses the frame
    at 17.9667 s): an exact time printed with 3 decimals can start the video a frame late."""
    return f'{max(0.0, (frame - .25) / fps):.6f}'


def cut_videos(pieces, a0, vd, fps=FPS):
    """one <video> per cutout piece inside [a0, a0 + vd). HyperFrames shows a video while start <= t <= start +
    duration and picks frame floor((t - start) * fps): the start is rounded down, the duration ends half a frame
    before the next piece, so every frame comes from exactly one piece."""
    f0, f1 = round(a0 * fps), round((a0 + vd) * fps)
    out = []
    for k, (a, b) in enumerate(pieces):
        lo, hi = max(a, f0), min(b, f1)
        if hi - lo < 1:
            continue
        out.append(f'<video id="cut{k}" class="full g cut" src="{piece_file(a, b)}" muted playsinline '
                   f'data-start="{floor6((lo - f0) / fps):.6f}" data-media-start="{media_start(lo - a) if lo > a else "0"}" '
                   f'data-duration="{(hi - lo - .5) / fps:.6f}" data-track-index="1"></video>')
    return out


def cutout_pieces(back_html, tweens):
    if L['subject'] != L['room']:   # the cutout is graded on its own (cool dude): every frame
        return cut_pieces([(0.0, DUR)], FRAMES, margin=0)
    return cut_pieces(list(shown_windows(html_ids(back_html), tweens, REEL_DUR).values()), FRAMES)


PIECES = []


def build():
    caps_html, back_html, front_html, s_tw = core()
    if L['fx'] == 'girl':   # cool girl: ✦ beside the chosen words
        sb_html, sf_html, sp_tw = sparkles()
        back_html, front_html, s_tw = back_html + sb_html, front_html + sf_html, s_tw + sp_tw
    f_html, f_tw = fx()
    c_html, c_tw = cutaways()
    p_html, p_tw = supers()
    e_html, e_tw = end_card()
    tweens = grades() + s_tw + f_tw + c_tw + p_tw + e_tw
    PIECES[:] = cutout_pieces(back_html, tweens)
    nl = '\n'
    a0, d = (RANGE[0], min(RANGE[1], REEL_DUR) - RANGE[0]) if RANGE else (0.0, REEL_DUR)
    vd = min(d, DUR - a0)   # the a-roll ends before an end card does
    vids = (f'    <video id="bgv" class="full g" src="assets/aroll.mp4" muted playsinline data-start="0" '
            f'data-media-start="{media_start(round(a0 * FPS))}" data-duration="{vd:.3f}" data-track-index="0"></video>\n') if vd > .02 else ''
    cuts = cut_videos(PIECES, a0, vd) if vd > .02 else []
    cutv = f'    <div id="cutwrap">{"".join(cuts)}</div>\n' if cuts else ''
    if cuts:
        tweens.insert(1, f"gsap.set('.cut',{{filter:'{L['subject']}'}});")
    sound = '' if RANGE else (f'  <audio id="bga" src="assets/voice.m4a" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" '
                              f'data-track-index="2" data-volume="1"></audio>\n' + nl.join(audio()))
    # chunk: the full timeline stays as built; a wrapper maps chunk time t -> reel time a0 + t
    register = (f'const main = gsap.timeline({{ paused: true }});\nmain.add(tl.tweenFromTo({a0:.4f}, {a0 + d:.4f}, {{ ease: "none" }}), 0);\n'
                f'window.__timelines["main"] = main;') if RANGE else 'window.__timelines["main"] = tl;'
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{d:.3f}" data-width="1080" data-height="1920">
{sound}
  <div id="stage">
{vids}{nl.join(back_html)}
{cutv}  </div>
  {FX_LAYERS[L['fx']][0]}
{nl.join(f_html)}
{nl.join(c_html)}
{nl.join(front_html)}
{nl.join(caps_html)}
{nl.join(p_html)}
{nl.join(e_html)}
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tweens)}
tl.set({{}}, {{}}, {REEL_DUR:.3f});
{register}
</script>
</body>
</html>
'''


# utf-8 on every OS: the page declares charset UTF-8, and Windows would otherwise write cp1252 (broken accents, emoji)
OUT = f'chunk_{round(RANGE[0] * 30):05d}.html' if RANGE else 'index.html'   # named by first frame
with open(OUT, 'w', encoding='utf-8', newline='\n') as _f:
    _f.write(build())
os.makedirs('work', exist_ok=True)
with open('work/reel.json', 'w', encoding='utf-8') as _f:   # for scripts/render.py: length + the audio mix
    json.dump({'look': LOOK, 'aroll_dur': DUR, 'reel_dur': round(REEL_DUR, 4), 'frames': round(REEL_DUR * 30),
               'sfx': [{'name': n, 't': round(t, 3), 'dur': round(min(SFX_LEN[n], REEL_DUR - t), 3), 'vol': round(v * SFX_GAIN, 3)}
                       for n, t, v in SFX]}, _f, indent=1)
if not RANGE:   # for scripts/cutout.py: the pieces this page shows
    with open('work/cutout_plan.json', 'w', encoding='utf-8') as _f:
        json.dump({'fps': FPS, 'frames': FRAMES, 'every_frame': L['subject'] != L['room'],
                   'pieces': [{'a': a, 'b': b, 'file': piece_file(a, b)} for a, b in PIECES]}, _f, indent=1)
if '--plan' in sys.argv:
    for g in caps_groups():
        print(f"{g['sid']} {g['words'][0][0]:6.2f}-{g['end']:6.2f}  {' '.join(w for _, w in g['words'])}")
    print(('PUNCH (automatic picks, review them):' if not PUNCH else 'PUNCH:'))
    for idx, t, text, it in PUNCHES:
        print(f"  ({t:.2f}, {norm(WORDS[idx[0]]['text'])!r}, {text!r}, {it}),   # {WORDS[idx[0]]['seg']}")
    if L['fx'] == 'girl':
        print(f"SPARKLE {'(automatic)' if SPARKLE is None else ''}: {sparkle_picks()}   SCRIPT_PUNCH: {sorted(SCRIPT_PUNCH) or 'none'}")
    for c in CUTAWAYS:
        print(f"cutaway {c['id']:8s} {c['a']:6.2f}-{c['b']:6.2f}  " + (f"{c['w']}x{c['h']} at ({c['x']},{c['y']}) {c['image']}" if c['kind'] == 'card' else 'split'))
print(f"wrote {OUT}  look {LOOK}  reel {REEL_DUR:.3f}s (a-roll {DUR:.3f}s)  {len(CUTS)} cuts  {len(PUNCHES)} punch words"
      + (f"  {len(CUTAWAYS)} cutaways  {len(SUPERS)} supers{'  end card' if ENDC else ''}" if PLAN else ''))
if not RANGE:
    _missing = [piece_file(a, b) for a, b in PIECES if not os.path.isfile(piece_file(a, b))]
    print(f"cutout: {sum(b - a for a, b in PIECES)} of {FRAMES} frames in {len(PIECES)} pieces"
          + (f"  ({len(_missing)} not cut out yet: run scripts/cutout.py before snapshots and the render)" if _missing else '  (all cut out)'))
