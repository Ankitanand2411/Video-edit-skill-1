#!/usr/bin/env python3
"""/video-edit template: a talking-head reel with every spoken word on screen, punch words tucked behind the head,
and (when the project has storyboard_plan.json) the storyboard's pictures, the graphics its VISUALS describe (stamp,
split, flow, stat, map: dark panels above the head, each element on its word), its supers and its end card.
It is the finished build of a real reel ("how handwriting helps the brain learn to read": one 87s phone clip + a
5-scene storyboard -> a 68s cool dude reel). Copy it into the project; set the CONTENT block; run it.

Inputs (written by the skill's scripts, nothing to hand-type):
  segments.json (assemble.py)   words.json (align.py)   headpos.json (headpos.py)   storyboard_plan.json (optional,
  storyboard_plan.py)   assets/aroll.mp4  assets/subject/*.webm (cutout.py)  assets/voice.m4a (assemble.py)
  assets/fonts/metrics.json (font metrics: placement and line widths are computed, not eyeballed)
CONTENT to set per reel: LOOK, PUNCH (empty = automatic picks, printed: review them), FIX, IMPACT, and in the cool
girl look SCRIPT_PUNCH (a punch word set in handwriting with a drawn underline) and SPARKLE (None = automatic picks).
MACHINERY (keep): looks, caption lines, behind-head placement, storyboard layer, graphics layer, grades, audio lanes,
--range, SAFE_GUIDE. assets/icons (platform icons, CC0) and assets/map (world map, public domain) feed the graphics.

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
import math
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
BRAND = None       # 'afterschool' | 'schooladvisor' | None: the storyboard's brand (storyboard.json "brand"), else none

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
GFX = [dict(g) for g in (PLAN or {}).get('graphics', [])]   # storyboard VISUALS drawn as graphics (graphics layer below)
GFX_WIN = [w for g in GFX for w in [(g['a'], g['b'])] + ([(g['then']['a'], g['then']['b'])] if g.get('then') else [])]
CAPS_LOW = bool(GFX)   # the graphics own the wall space above the head: the running captions move under the face
CHEST = {'wide': 1240, 'close': 1310}   # caption line under the chin (1080x1920), above the lower-third plates at 1398
SB_DOC = load('storyboard.json') or {}
STRICT = bool(PLAN) and any(sc.get('script') for sc in SB_DOC.get('scenes', []))
# storyboard mode: the storyboard is the source of truth for every word on screen. Captions take each word's spelling
# and capitals from its SCRIPT; supers, labels and graphic text appear exactly as written (no forced caps or lower case)

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
MOOD = (PLAN or {}).get('mood', '').lower()
if re.search(r'vibrant|bright|energetic|colou?rful|upbeat', MOOD):   # the storyboard's MOOD sets the grade too
    for _k in ('room', 'subject'):
        L[_k] += ' saturate(1.08) brightness(1.03)'
elif re.search(r'moody|dark|serious|sombre|somber|dramatic', MOOD):
    for _k in ('room', 'subject'):
        L[_k] += ' saturate(.94) brightness(.97)'
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
    if CAPS_LOW:
        return CHEST[shot(sid)]
    k, xh, cap = pmet()
    s0 = PU['size'][shot(sid)]
    return round(max(228, min(CAPS_MAX[shot(sid)], min(head_samples(sid)) + (.2 * xh - 1.05 * cap) * s0 - CAP_LH - 24)))


def top_limit(sid):
    """highest y a word or card above the head may reach: under the caption line, or the safe top when it sits low"""
    return 228 if CAPS_LOW else caps_top(sid) + CAP_LH + 24


def gfx_at(a, b):
    return any(x < b and a < y for x, y in GFX_WIN)


SMALL = .55        # a behind-head word under 55% of the look's size reads as a mistake: build.py says so
SMALL_WORDS = []
IG_COLUMN_X, IG_COLUMN_Y, IG_BOTTOM = 980, 1155, 1470   # Instagram's like / comment / share column, caption bar


def under_card(text, it, win):
    """-> (size, top) of a punch word in front, under a cutaway card. Centred and up to SERIF_W wide, it ran into
    Instagram's like / comment / share column (x 980+ from y 1155) when the card sat low: there it keeps inside
    x 100-980. No room left above the caption bar (y 1470): above the card instead."""
    w1 = text_width(text, 1, PU['font_it'] if it else PU['font'], PU['track'], .04)
    size = int(min(150, SERIF_W / w1))
    top = win['y'] + win['h'] + 2 * BORDER + 16
    if top + size * PU['lh'] > IG_COLUMN_Y:
        size = int(min(size, 2 * (IG_COLUMN_X - 540) / w1))
    if top + size * PU['lh'] > IG_BOTTOM:
        top = max(220, round(win['y'] - 16 - size * PU['lh']))
    return size, top


def behind_head(sid, a, b, text, it):
    """-> (top, size) of a punch word tucked behind the head while it is on screen"""
    k, xh, cap = pmet(it)
    hd = min(head_at(sid, a), head_at(sid, min(b, a + .6)))   # highest the head gets while the word lands
    pad = .04 if PU['anim'] == 'mask' else 0
    fit = SERIF_W / text_width(text, 1, PU['font_it'] if it else PU['font'], PU['track'], pad)
    clear = (hd - top_limit(sid)) / (1.05 * cap - .2 * xh)
    size = int(min(PU['size'][shot(sid)], fit, clear))
    return round(hd + (.2 * xh - k) * size), size


# ------------------------------------------------------------------ words + punch words
STOP = set("a an and the of to in on at by for with from as is it its it's be are was were this that these those i we you they he "
           "she my our your their me us them so but or if then than too very just can could would will about into over up down out "
           "not no yes all some any each every while when where what which who how before after because really actually even also "
           "maybe kind lot get got do does did have has had being been know thing things there here like much many more most part "
           "well way still only there's they're doesn't don't can't won't isn't aren't it's that's here's what's another "
           "i'm you're we're".split())


def proper_words():
    """words a lower-case look keeps capitalised: capitalised inside a sentence somewhere (the EDL lines, the
    storyboard script), and the names the graphics show. The first reel from a news storyboard printed "tiktok",
    "mcmc", "unicef" and "australia"."""
    texts = [s.get('line', '') for s in (load('edl.json') or [])]
    texts += [s.get('script', '') for s in (load('storyboard.json') or {}).get('scenes', [])]
    out = set()
    for t in texts:
        start = True
        for tok in re.findall(r"[\w'’-]+|[.?!:]", t):
            if tok in '.?!:':   # a capital after a colon opens a sentence too ("the real question: Are we")
                start = True; continue
            base = re.sub(r"[^\w-]", '', tok.split("'")[0].split('’')[0]).lower()
            if not start and tok[:1].isupper() and base not in STOP:
                out.add(base)
            start = False
    for g in GFX:
        for n in g.get('apps', []) + [i for sd in g.get('sides', []) for i in sd['items']] + g.get('places', []) + g.get('targets', []):
            out.update(x.lower() for x in re.findall(r'\w+', n))
    return out


PROPER = proper_words()


def shown(text):
    """a word as a lower-case look shows it: lower case, except names (TikTok, MCMC, Malaysia's) and "I" """
    core = re.sub(r"[^\w'’-]", '', text)
    base = re.sub(r"[^\w-]", '', core.split("'")[0].split('’')[0]).lower()
    if base == 'i' or core[:1].isupper() and base in PROPER or any(c.isupper() for c in core[1:]):
        return text
    return text.lower()


def bare(t):
    """a word without punctuation, its digit grouping kept: "100,000" stays, "TikTok," -> "TikTok" (the first news reel
    captioned "100000")"""
    return re.sub(r"[^\w'’,.-]|[,.](?!\d)|(?<!\d)[,.]", '', t)


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
    for w in out:   # captions in sentence case, as the line writes them (shown() is the punch words' lower case)
        w['shown'] = w['text']
    return out


WORDS = load_words()


def norm(t):
    return re.sub(r"[^\w'-]", '', t).lower()


def skill_module(name):
    """a module from the skill's own scripts, found through $VIDEO_EDIT_SKILL or ~/.claude/skills/video-edit; None
    when the skill is not there (the build then works as before)"""
    import importlib.util
    for d in (os.environ.get('VIDEO_EDIT_SKILL', ''), os.path.join(os.path.expanduser('~'), '.claude', 'skills', 'video-edit')):
        f = os.path.join(d, 'scripts', f'{name}.py')
        if d and os.path.isfile(f):
            spec = importlib.util.spec_from_file_location(f'skill_{name}', f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


SPELL = skill_module('spelling')   # British English on screen: "recognising", never Whisper's "recognizing"


def same_word(a, b):
    """caption word == punch key word, whatever the spelling (British captions, a key typed the American way)"""
    return SPELL.key(a) == SPELL.key(b) if SPELL else norm(a) == norm(b)


def british(text):
    """a punch word / super typed for the screen, in British spelling (scripts/spelling.py)"""
    return SPELL.british_text(text) if SPELL else text


def script_tokens():
    """the storyboard SCRIPT word by word: [(word, as written with its punctuation)] ("Gaming", "win,", "100,000")"""
    out = []
    for sc in SB_DOC.get('scenes', []):
        for tok in re.sub(r'\s*[—–]\s*', ', ', sc.get('script', '')).split():   # no em dashes on screen
            core = re.match(r"^\W*(.*?)\W*$", tok).group(1)
            if re.search(r'\w', core):
                mark = re.search(r'[.,?!;:]', tok[tok.index(core) + len(core):])
                out.append((core, core + (mark.group(0) if mark else '')))
    return out


SWAPS = []   # spoken words shown as the script's (a slip of a word or two): printed for review


def storyboard_forms():
    """storyboard mode: every spoken word the SCRIPT has too is shown as the script writes it, with its punctuation
    (aligned in order, spelling-blind: "deputy police chief" said is "Deputy Police Chief" written, "radicalisation" is
    "radicalization"); words the script does not have are shown as the EDL line writes them. -> (matched, spoken)"""
    import difflib
    toks = script_tokens()
    key = SPELL.key if SPELL else norm
    hits = 0
    ops = difflib.SequenceMatcher(None, [key(w['text']) for w in WORDS], [key(t) for t, _ in toks], autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        # the same words, or a slip of a word or two inside a sentence the script has ("over there" said, "over this"
        # written; "have" / "has"): the script's grammar and punctuation, on the spoken word's timing
        if op == 'equal' or op == 'replace' and i2 - i1 == j2 - j1 <= 2:
            for k in range(i2 - i1):
                WORDS[i1 + k]['shown'] = toks[j1 + k][1]
                hits += 1
                if op == 'replace':
                    SWAPS.append(f"{WORDS[i1 + k]['text']!r} said -> {toks[j1 + k][1]!r} (script)")
    return hits, len(WORDS)


if STRICT:
    for _w in WORDS:
        _w['shown'] = _w['text']   # the EDL line's own case for words the script does not have
    SB_TEXT = storyboard_forms()


# the CONTENT settings that name a punch word by its display text follow it into British spelling
SCRIPT_PUNCH = {british(t) for t in SCRIPT_PUNCH}
SPARKLE = {british(t): d for t, d in SPARKLE.items()} if SPARKLE else SPARKLE
IMPACT = british(IMPACT) if IMPACT else IMPACT


VAGUE = set("interesting important different genuine simply amazing incredible special really actually basically definitely "
            "certainly probably obviously quite pretty whole entire making taking having getting doing saying".split())
FILLER = set("started holding everything something anything apparently properly across today found thought wanted going "
             "remember looked looking little really things right being doing making saying getting".split())


def sb_keywords():
    sb = load('storyboard.json') or {}
    text = ' '.join(s.get('script', '') + ' ' + s.get('super', '') + ' ' + ' '.join(s.get('visuals', [])) for s in sb.get('scenes', []))
    return {norm(w).rstrip('s') for w in re.findall(r"[\w'-]+", text) if len(w) > 2}


def sb_phrases():
    """storyboard mode: the phrases its SUPERs and quoted VISUALS give (1-3 words, as keys): the punch words come from
    these first ("classroom hours", "resident tutors", "1843"), not from whatever long word a shot happens to have"""
    texts = []
    for sc in SB_DOC.get('scenes', []):
        texts.append(sc.get('super', ''))
        texts += re.findall(r'["“”]([^"“”]{1,80})["“”]', ' '.join(sc.get('visuals', [])))
    out, kf = set(), (SPELL.key if SPELL else norm)
    for t in texts:
        toks = [kf(x) for x in re.findall(r"[\w'’-]+", t)]
        for n in (3, 2, 1):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] not in STOP and g[-1] not in STOP and (n > 1 or len(g[0]) > 3 or g[0].isdigit()):   # no "the", "of" ends
                    out.add(tuple(g))
    return out


def auto_punch():
    """no PUNCH given: per shot the word that carries the line, 2 on shots over 3.8s (1.4s apart), none under 1.2s.
    Score: in the storyboard (script / super / visuals) +10, a number +8, ends a phrase +3 (. ? !) or +2 (,), length
    up to +10, -ly adverbs and filler verbs -8. Review the printed picks: the editor's choice beats any heuristic."""
    kw, out = sb_keywords(), []
    phrases = sb_phrases() if STRICT else set()
    for sid in ORDER:
        dur = END[sid] - T[sid]
        if dur < 1.2:
            continue
        mine = [k for k, w in enumerate(WORDS) if w['seg'] == sid]
        took = []
        for n in (3, 2, 1):   # a storyboard phrase said in this shot: that is the punch word
            for k in mine:
                g = tuple((SPELL.key if SPELL else norm)(WORDS[k + j]['text']) for j in range(n) if k + j in mine)
                if len(g) == n and g in phrases and len(took) < (2 if dur > 3.8 else 1) and not gfx_at(WORDS[k]['start'] - .05, WORDS[k]['start'] + .7) \
                        and all(abs(WORDS[k]['start'] - WORDS[q]['start']) > 1.4 for q, _ in took):
                    took.append((k, n))
        for k, n in took:
            end = WORDS[k + n - 1]['text'].rstrip()[-1:]
            out.append((WORDS[k]['start'], ' '.join(norm(WORDS[k + j]['text']) for j in range(n)),
                        ' '.join(bare(WORDS[k + j]['shown']) for j in range(n)) + (end if end in '.?!' else ''), False))
        if took:
            continue
        cands = []
        for w in WORDS:
            n = norm(w['text'])
            if w['seg'] != sid or n in STOP or len(n) < 3 or (len(n) < 5 and not n.isdigit() and n.rstrip('s') not in kw):
                continue
            if gfx_at(w['start'] - .05, w['start'] + .7):   # a graphic owns the space above the head then
                continue
            end = w['text'].rstrip()[-1:]
            score = (10 * (n.rstrip('s') in kw) + 8 * n.isdigit() + (3 if end in '.?!' else 2 if end == ',' else 0) + min(len(n), 10)
                     - 8 * (n.endswith('ly') or n in FILLER) - 6 * (n in VAGUE) + 5 * (w['text'][:1].isupper() and n not in STOP))
            cands.append((score, w))
        picked = []
        for score, w in sorted(cands, key=lambda c: -c[0]):
            if score >= 6 and len(picked) < (2 if dur > 3.8 else 1) and all(abs(w['start'] - q['start']) > 1.4 for q in picked):
                picked.append(w)
        for w in sorted(picked, key=lambda w: w['start']):
            # the word as the thought lands: its ? or ! or . kept, its article with it ("a win?", "a stranger")
            k = WORDS.index(w)
            art = WORDS[k - 1] if k and WORDS[k - 1]['seg'] == sid and norm(WORDS[k - 1]['text']) in ('a', 'an', 'the') else None
            end = w['text'].rstrip()[-1:]
            disp = bare(w['shown'] if STRICT else shown(w['text'])) + (end if end in '.?!' else '')
            key = norm(w['text'])
            if art:
                disp, key = f"{norm(art['text'])} {disp}", f"{norm(art['text'])} {key}"
            out.append(((art or w)['start'], key, disp, False))
    return out


def resolve_punch():
    """-> sorted [(word indices, start, display text, italic)], each matched to the nearest spoken occurrence"""
    found = []
    for hint, key, text, it in (PUNCH or auto_punch()):
        toks = key.lower().split()
        cands = [i for i, w in enumerate(WORDS) if same_word(w['text'], toks[0]) and abs(w['start'] - hint) < 1.5
                 and all(i + k < len(WORDS) and same_word(WORDS[i + k]['text'], tk) for k, tk in enumerate(toks))]
        if not cands:
            sys.exit(f'PUNCH word not found: {key!r} near {hint}s')
        i = min(cands, key=lambda c: abs(WORDS[c]['start'] - hint))
        it = PU['italic'] if PU['italic'] is not None else it
        lead, mid, trail = re.match(r"^(\W*)(.*?)(\W*)$", text).groups()
        said = [WORDS[i + k] for k in range(len(toks))]
        if len(mid.split()) == len(said) and all(same_word(a, b['text']) for a, b in zip(mid.split(), said)):
            # storyboard mode: the words as the storyboard writes them; otherwise a name keeps its capital ("malaysia's"
            # typed for the punch word went out lower case twice in one reel)
            text = lead + ' '.join(bare(w['shown']) if STRICT else bare(shown(w['text'])) if x.islower() and
                                   bare(shown(w['text'])).lower() == x.lower() else british(x) for x, w in zip(mid.split(), said)) + trail
        else:
            text = british(text)
        found.append((list(range(i, i + len(toks))), WORDS[i]['start'], text if PU['case'] != 'upper' else text.upper(), it))
    return sorted(found, key=lambda p: p[1])


PUNCHES = resolve_punch()
PUNCH_IDX = {i for p in PUNCHES for i in p[0]}


def punch_t(text):
    return next((p[1] for p in PUNCHES if p[2] == text), None)


# ------------------------------------------------------------------ caption lines (balanced by measured width)
def cap_text(t):
    """a caption word: sentence case as written, its full stop / comma / question mark kept ("Sounds like a win,")"""
    mark = re.search(r'[.,?!;:](?=[\'"”’)\]]*$)', t)
    t = bare(t) + (mark.group(0) if mark else '')
    return t.upper() if CAP['case'] == 'upper' else t


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
        if cur and (cur[-1]['seg'] != w['seg'] or w['start'] - prev['end'] > .45 or prev['shown'].rstrip('\'"”’)')[-1:] in '.,?!'):
            phrases.append(cur); cur = []
        cur.append(w)
        prev = w
    if cur:
        phrases.append(cur)
    groups = []
    for ph in phrases:
        txts = [cap_text(w['shown']) for w in ph]
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


def card_html(cid, src, x, y, w, h, z, inner='', push=1.0):
    """a picture card drawn 1:1; push > 1: the copy is that much bigger (never past the picture's own size) for a
    zoom the storyboard asks for, cropped by the card"""
    if push > 1:
        W, H = round(w * push), round(h * push)
        img = (f'<img class="pz" src="{display_copy(src, W, H)}" width="{W}" height="{H}" alt="" '
               f'style="margin:{-(H - h) // 2}px 0 0 {-(W - w) // 2}px">')
    else:
        img = f'<img src="{display_copy(src, w, h)}" width="{w}" height="{h}" alt="">'
    return (f'<div id="{cid}" class="card" style="left:{x}px;top:{y}px;width:{w + 2 * BORDER}px;height:{h + 2 * BORDER}px;z-index:{z}">'
            f'{img}{inner}</div>')


def card_in(sel, t, anim):
    """a card's entrance as the storyboard words it: slide from a side, pop, fade, flip; else a soft rise"""
    move = {'slide-left': 'x:-280', 'slide-right': 'x:280', 'slide-down': 'y:-220', 'slide-up': 'y:220'}.get(anim)
    if move:
        return [f"tl.fromTo('{sel}',{{autoAlpha:0,{move}}},{{autoAlpha:1,x:0,y:0,duration:.5,ease:'power3.out',immediateRender:false}},{t:.3f});",
                f"tl.set('{sel}',{{clearProps:'transform'}},{t + .52:.3f});"]
    if anim == 'pop':
        return [f"tl.fromTo('{sel}',{{autoAlpha:0,scale:.6}},{{autoAlpha:1,scale:1,duration:.45,ease:'back.out(1.8)',immediateRender:false}},{t:.3f});",
                f"tl.set('{sel}',{{clearProps:'transform'}},{t + .47:.3f});"]
    if anim == 'fade':
        return [f"tl.fromTo('{sel}',{{autoAlpha:0}},{{autoAlpha:1,duration:.5,ease:'power1.out',immediateRender:false}},{t:.3f});"]
    if anim == 'flip':
        return [f"tl.fromTo('{sel}',{{autoAlpha:0,rotationY:-80,transformPerspective:1200}},{{autoAlpha:1,rotationY:0,duration:.55,"
                f"ease:'power3.out',immediateRender:false}},{t:.3f});", f"tl.set('{sel}',{{clearProps:'transform'}},{t + .57:.3f});"]
    return rise_in(sel, t)


for _c in CUTAWAYS:   # a punch word gets ~1s on screen before a cutaway covers it (keep >= 2s of cutaway)
    for _p in PUNCHES:
        if (_c['a'] - 1.0 < _p[1] < _c['a'] and _c['b'] - (_p[1] + 1.0) >= 2.0
                and seg_at(_p[1]) == seg_at(_c['a'] + .02)):   # a word in the previous shot ends at the cut anyway
            _c['a'] = round(_p[1] + 1.0, 3)
for _c in CUTAWAYS:   # card rectangles, integer pixels, under the caption line of the shot the cutaway opens on
    if _c['kind'] == 'card':
        _top = top_limit(seg_at(_c['a'] + .02)) + 4
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
            anim = c.get('anim', '')
            nw, nh = img_size(c['image'])
            push = min(1.08, nw / c['w'], nh / c['h']) if anim in ('push', 'pull') else 1.0   # never past its own size
            html.append(card_html(f'{cid}-card', c['image'], c['x'], c['y'], c['w'], c['h'], 11, push=push))
            tw.append(f"gsap.set(['#{cid}-bg','#{cid}-card'],{{autoAlpha:0}});")
            tw += ([f"tl.set('#{cid}-bg',{{autoAlpha:1}},{a:.3f});"] if at_cut(a) else
                   [f"tl.fromTo('#{cid}-bg',{{autoAlpha:0}},{{autoAlpha:1,duration:.22,ease:'power1.out',immediateRender:false}},{a:.3f});"])
            tw += card_in(f'#{cid}-card', a + .04, anim) + hide(f'#{cid}-bg,#{cid}-card', b, at_cut(b))
            if push > 1.001:   # "slow zoom in" / "zoom out": the picture moves inside its card the whole time
                z0, z1 = (1 / push, 1) if anim == 'push' else (1, 1 / push)
                tw.append(f"tl.fromTo('#{cid}-card .pz',{{scale:{z0:.4f}}},{{scale:{z1:.4f},duration:{b - a:.3f},ease:'none',"
                          f"immediateRender:false}},{a:.3f});")
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
            tw += [f"tl.fromTo('#{cid}-l{n}',{{autoAlpha:0,x:-10}},{{autoAlpha:1,x:0,duration:.3,ease:'power2.out',immediateRender:false}},"
                   f"{t:.3f});" for n, t in enumerate(c['label_t'])]
            tw += punch_in(f'#{cid}-vs', c['vs_t']) + hide(f'#{cid}-bg,#{cid}-c0,#{cid}-c1,#{cid}-vs', b, at_cut(b))
    return html, tw


ARROW = ('<svg width="34" height="14" viewBox="0 0 34 14"><path d="M1 7h30M25 1.5 31.5 7 25 12.5" fill="none" stroke="currentColor" '
         'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')   # the fonts carry no arrow glyph


BRANDS = {   # the brand's own text box: the team's brand packs (Afterschool: primary_deep for boxes and buttons;
             # School Advisor: royal blue, its 60% family), white text on both
    'afterschool': {'name': 'Afterschool', 'box': '#413370', 'text': '#FFFFFF'},
    'schooladvisor': {'name': 'School Advisor', 'box': '#113DA5', 'text': '#FFFFFF'},
}
BR = BRANDS.get(globals().get('BRAND') or (PLAN or {}).get('brand') or '')   # an older CONTENT block has no BRAND
PLATE_LIT, PLATE_DONE = (BR['text'], BR['text']) if BR else (YEL, CREAM)
PLATE_W = 880   # widest a plate may be: centred, it stays clear of the safe sides and Instagram's icon column


def plate_fit(words, mc, icon=False, arrows=0):
    """CSS that keeps a SUPER plate inside the frame. A delivered reel's plate ("DEBATED IN PARLIAMENT · FIXED VS.
    SHIFTING GRADES") ran off both sides: the size comes down to fit, and below a readable size the plate wraps onto
    two lines."""
    if L['fx'] == 'girl':
        font, size, track, gap, small = 'InstrumentSerif-400-italic', 50, 0, .12, 36
    elif mc:
        font, size, track, gap, small = 'Montserrat-600-normal', 29, .02, .22, 22
    else:
        font, size, track, gap, small = 'Montserrat-500-normal', 26, .24, .22, 20
    per_em = sum(text_width(w, 1, font, track) + 2 * gap for w in words) + arrows * (34 / size + .87)
    room = PLATE_W - 60 - (40 if icon else 0)
    if per_em * size <= room:
        return ''
    fit = int(room / per_em)
    if fit >= small:
        return f'font-size:{fit}px'
    return f'font-size:{small}px;white-space:normal;max-width:{PLATE_W}px;line-height:1.45;border-radius:26px'


def lt_style(fit):
    """a plate that wraps grows upwards from the bottom of the safe zone (y 1466) instead of down into the caption bar"""
    return ' style="top:auto;bottom:454px"' if 'white-space:normal' in fit else ''


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
            fit = plate_fit([w for _, w in s['steps']], s['steps'][0][1].upper() != s['steps'][0][1], arrows=len(s['steps']) - 1)
            html.append(f'<div class="lt"{lt_style(fit)}><div id="{sid_}" class="plate" style="{fit}">{"".join(parts)}</div></div>')
            tw += [f"gsap.set('#{sid_}',{{autoAlpha:0}});", f"gsap.set('#{sid_} .st, #{sid_} .ar',{{autoAlpha:.35}});",
                   f"tl.fromTo('#{sid_}',{{autoAlpha:0,y:16}},{{autoAlpha:1,y:0,duration:.35,ease:'power3.out',immediateRender:false}},{a + .15:.3f});"]
            for k, (t, _) in enumerate(s['steps']):   # a step lights up: colour and opacity only, no blur, no stretch
                if k:
                    tw += [f"tl.to('#{sid_}-a{k}',{{autoAlpha:1,duration:.25}},{t - .1:.3f});",
                           f"tl.to('#{sid_}-s{k - 1}',{{color:'{PLATE_DONE}',duration:.2}},{t - .04:.3f});"]
                tw += [f"tl.to('#{sid_}-s{k}',{{autoAlpha:1,color:'{PLATE_LIT}',duration:.22,ease:'power1.out'}},{t - .04:.3f});"]
        else:
            words = s['text'].split()
            spans = ''.join(f'<span id="{sid_}-w{k}" class="st{" y" if k >= len(words) - s.get("yellow_last", 0) else ""}">{w}</span>'
                            for k, w in enumerate(words))
            icon = f'<span class="pi">{SVG[s["icon"]]}</span>' if s.get('icon') in SVG else ''   # the SUPER's emoji, drawn
            mc = '' if s['text'].upper() == s['text'] else ' mc'   # mixed case (as the storyboard wrote it): no caps tracking
            fit = plate_fit(words, bool(mc), icon=bool(icon))
            html.append(f'<div class="lt"{lt_style(fit)}><div id="{sid_}" class="plate words{mc}" style="{fit}">{icon}{spans}</div></div>')
            tw += [f"gsap.set('#{sid_}',{{autoAlpha:0}});", f"gsap.set('#{sid_} .st',{{autoAlpha:0}});",
                   f"tl.fromTo('#{sid_}',{{autoAlpha:0}},{{autoAlpha:1,duration:.25,immediateRender:false}},{a:.3f});",
                   f"tl.fromTo('#{sid_} .st',{{autoAlpha:0,y:8}},{{autoAlpha:1,y:0,duration:.3,ease:'power2.out',stagger:.04,"
                   f"immediateRender:false}},{a + .05:.3f});"]   # no blur / stretch: it read as the plate glitching
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
    if ENDC.get('cta'):   # the closing frame: a verb pill (tapped), the name, the tagline
        c = ENDC['cta']
        y = top + 60 if ENDC.get('image') else 700
        name = c.get('name') or ''
        ns = int(min(128, SERIF_W / max(1e-6, text_width(name, 1, 'InterTight-900-normal'))))
        if c.get('verb'):
            inner.append(f'<div id="end-v" class="ctp" style="top:{y}px">{c["verb"]}</div><div id="end-tap" class="tap" style="top:{y + 6}px"></div>')
            y += 110
        inner.append(f'<div id="end-n" class="ctn" style="top:{y}px;font-size:{ns}px">{name}</div>')
        y += round(ns * 1.12)
        sub = ' · '.join(x for x in (c.get('tagline', ''), c.get('handle', '')) if x)
        if sub:
            inner.append(f'<div id="end-t" class="ctt" style="top:{y + 8}px">{sub}</div>')
        tw += ["gsap.set(['#end-v','#end-n','#end-t','#end-tap'],{autoAlpha:0});"]
        if c.get('verb'):
            tw += [pop('#end-v', END_IN + .3, .4, 'scale:.5'),
                   f"tl.fromTo('#end-tap',{{autoAlpha:.9,scale:.2}},{{autoAlpha:0,scale:1.6,duration:.55,ease:'power2.out',immediateRender:false}},{END_IN + 1.35:.3f});",
                   f"tl.fromTo('#end-v',{{scale:.9}},{{scale:1,duration:.3,ease:'back.out(2)',immediateRender:false}},{END_IN + 1.35:.3f});"]
        tw += [f"tl.fromTo('#end-n',{{autoAlpha:0,y:30}},{{autoAlpha:1,y:0,duration:.45,ease:'power3.out',immediateRender:false}},{END_IN + .5:.3f});"]
        if sub:
            tw += [f"tl.fromTo('#end-t',{{autoAlpha:0,y:14}},{{autoAlpha:1,y:0,duration:.4,ease:'power2.out',immediateRender:false}},{END_IN + .8:.3f});"]
    for k, line in enumerate(ENDC.get('lines', [])):
        it = k == len(ENDC['lines']) - 1 and len(ENDC['lines']) > 1   # the last line: italic, accent colour
        size = int(min(150, SERIF_W / text_width(line, 1, PU['font_it'] if it else PU['font'], PU['track'], .04)))
        inner.append(punch_div(f'end-l{k}', line, it or bool(PU['italic']), top, size, 'pw front',
                               YEL if it else ('#FFF8EF' if L['fx'] == 'girl' else None)))   # girl: only the last line yellow
        tw += punch_in(f'#end-l{k}', END_IN + .55 + .6 * k)
        top += round(size * 1.12)
    return [f'<div id="endc" style="z-index:20">{"".join(inner)}</div>'], tw


# ------------------------------------------------------------------ storyboard graphics (storyboard_plan.json 'graphics')
# VISUALS that describe a graphic, not a picture (scripts/sbgraphics.py): drawn here as dark panels in the wall space
# above the head, every element on the word that names it, the speaker in view the whole time. The first reel from a
# storyboard like this showed none of them (only pictures were understood); these are what the storyboard asked for.
GFX_TOP, GFX_W = 236, 940
GFX_X = (1080 - GFX_W) // 2
GOLD, RED, GREEN = '#F6D64A', '#EF4444', '#22C55E'
TONE = {'red': RED, 'green': GREEN, 'yellow': GOLD, 'blue': '#3B82F6'}
ICONS = load('assets/icons/icons.json', {})
MISSING = []      # storyboard VISUALS not on screen: work/reel.json carries them and render.py refuses to start
GFX_TIGHT = []    # graphics scaled down hard to clear a high head (a close-up under a graphic)
SVG = {   # small glyphs (the fonts have no emoji): plates, chips, locks, the flipped banner
    'no': '<svg width="28" height="28" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.3" fill="none" stroke="#EF4444" stroke-width="2.6"/>'
          '<path d="M5.6 18.4 18.4 5.6" stroke="#EF4444" stroke-width="2.6"/></svg>',
    'warn': '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M12 2.6 22.8 21.2H1.2Z" fill="#F6D64A"/>'
            '<path d="M12 9.2v5.6" stroke="#111" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="17.9" r="1.4" fill="#111"/></svg>',
    'gamepad': '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M7.2 6.5h9.6a5.2 5.2 0 0 1 5.1 6.2l-.8 4.1a2.7 2.7 0 0 1-4.7 '
               '1.2l-1.8-2.3H9.4l-1.8 2.3a2.7 2.7 0 0 1-4.7-1.2l-.8-4.1a5.2 5.2 0 0 1 5.1-6.2Z" fill="currentColor"/>'
               '<path d="M7.6 9.6v3.6M5.8 11.4h3.6" stroke="#0d1015" stroke-width="1.7" stroke-linecap="round"/>'
               '<circle cx="15.6" cy="10.4" r="1.05" fill="#0d1015"/><circle cx="17.6" cy="12.4" r="1.05" fill="#0d1015"/></svg>',
    'target': '<svg width="28" height="28" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.5" fill="none" stroke="#EF4444" stroke-width="2.4"/>'
              '<circle cx="12" cy="12" r="5.5" fill="none" stroke="#EF4444" stroke-width="2.4"/><circle cx="12" cy="12" r="1.8" fill="#EF4444"/></svg>',
    'phone': '<svg width="28" height="28" viewBox="0 0 24 24"><rect x="6.5" y="2" width="11" height="20" rx="2.6" fill="none" stroke="currentColor" '
             'stroke-width="2"/><path d="M10.5 18.5h3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    'check': '<svg width="28" height="28" viewBox="0 0 24 24"><path d="m4.5 12.5 4.8 4.8L19.5 7" fill="none" stroke="#22C55E" stroke-width="3" '
             'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    'cross': '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" stroke="#EF4444" stroke-width="3" stroke-linecap="round"/></svg>',
    'lock': '<svg width="16" height="16" viewBox="0 0 24 24"><rect x="4.5" y="10.5" width="15" height="11" rx="2.4" fill="#fff"/>'
            '<path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7" fill="none" stroke="#fff" stroke-width="2.6"/></svg>',
}


def icon_path(slug):
    try:
        with open(f'assets/icons/{slug}.svg', encoding='utf-8') as fh:
            return re.search(r'<path d="([^"]+)"', fh.read()).group(1)
    except (OSError, AttributeError):
        return None


def tile_w(art, size, wide=True):
    """a tile is square; a wide logo (a wordmark like Minecraft's) gets a wide tile, up to 2:1"""
    if wide and (art or {}).get('logo'):
        w, h = img_size(art['logo'])
        if w / h > 1.3:
            return round(size * min(2.0, w / h))
    return size


def tile_copy(src, w, h, cover):
    """exact-size copy for a tile, drawn 1:1: a photo fills it (centre crop), a logo fits inside it"""
    os.makedirs('assets/storyboard/disp', exist_ok=True)
    out = f"assets/storyboard/disp/{os.path.splitext(os.path.basename(src))[0]}_{'c' if cover else 'f'}{w}x{h}.png"
    if not os.path.exists(out):
        vf = (f'scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}' if cover else
              f'scale={w - 12}:{h - 12}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0d1015')
        subprocess.run([FF, '-v', 'error', '-y', '-i', src, '-vf', vf, '-frames:v', '1', '-pix_fmt', 'rgb24', out], check=True)
    return out


def tile(tid, name, art, size, label=True, x=0, y=0, wide=True):
    """an entity's tile: the folder's own logo (the user's file wins), else the platform icon on its brand colour,
    else the folder photo, else its initials"""
    art, r = art or {}, round(size * .24)
    w = tile_w(art, size, wide)
    box = f'width:{w}px;height:{size}px;border-radius:{r}px'
    if art.get('logo'):
        lw, lh = img_size(art['logo'])
        face = (f'<div class="tl" style="{box};background:#0d1015"><img src="{tile_copy(art["logo"], w, size, abs(lw / lh - w / size) < .15)}" '
                f'width="{w}" height="{size}" alt=""></div>')
    elif art.get('icon') and icon_path(art['icon']):
        c = ICONS.get(art['icon'], {'bg': '#111111', 'fg': '#FFFFFF'})
        bg = ('radial-gradient(circle at 30% 107%,#fdf497 0%,#fdf497 5%,#fd5949 45%,#d6249f 60%,#285AEB 90%)'
              if art['icon'] == 'instagram' else c['bg'])
        g = round(size * .52)
        face = (f'<div class="tl" style="{box};background:{bg}"><svg width="{g}" height="{g}" viewBox="0 0 24 24">'
                f'<path d="{icon_path(art["icon"])}" fill="{c["fg"]}"/></svg></div>')
    elif art.get('photo'):
        face = f'<div class="tl" style="{box}"><img src="{tile_copy(art["photo"], w, size, True)}" width="{w}" height="{size}" alt=""></div>'
    else:
        face = (f'<div class="tl" style="{box};background:#2a2f39;color:#fff;font:800 {round(size * .36)}px \'Inter Tight\'">'
                f'{re.sub(r"[^A-Za-z0-9]", "", name)[:2]}</div>')
    lab = f'<div class="tn">{name}</div>' if label else ''
    return f'<div id="{tid}" class="ti" style="left:{x}px;top:{y}px;width:{w}px">{face}{lab}</div>'


def chip(cid, text, color, x=None, y=0, icon=''):
    pos = f'left:{x}px' if x is not None else 'left:50%;margin-left:0;transform:translateX(-50%)'
    return (f'<div id="{cid}" class="chip" style="{pos};top:{y}px;color:{color}">{SVG.get(icon, "")}<span>{text}</span></div>')


def pop(sel, t, dur=.34, frm='scale:.4', ease='back.out(2)'):
    return f"tl.fromTo('{sel}',{{autoAlpha:0,{frm}}},{{autoAlpha:1,scale:1,duration:{dur},ease:'{ease}',immediateRender:false}},{t:.3f});"


def show(gid, a, b):
    """a graphic's panel in (fade + rise) at a, out at b"""
    return ([f"tl.fromTo('#{gid} .gi',{{autoAlpha:0,y:34,scale:.97}},{{autoAlpha:1,y:0,scale:1,duration:.45,ease:'power3.out',immediateRender:false}},{a:.3f});"]
            + hide(f'#{gid} .gi', b, at_cut(b), .25))


def g_stamp(g):
    gid, html, tw = g['id'], [], []
    apps = g.get('apps', [])[:6]
    pw, ph = 250, 430
    px = (GFX_W - pw) // 2
    cells, ts = [], 58
    for k in range(12):
        cx, cy = 22 + (k % 3) * (ts + 16), 64 + (k // 3) * (ts + 18)
        if k < len(apps):
            cells.append(tile(f'{gid}-a{k}', apps[k], g['art'].get(apps[k]), ts, False, cx, cy, wide=False)
                         + (f'<div id="{gid}-k{k}" class="lk" style="left:{cx + ts - 20}px;top:{cy - 10}px">{SVG["lock"]}</div>' if g.get('locks') else ''))
        else:
            cells.append(f'<div class="ph0" style="left:{cx}px;top:{cy}px;width:{ts}px;height:{ts}px"></div>')
    game = (f'<div id="{gid}-gm" class="gm" style="left:{(pw - 120) // 2}px;top:{ph - 170}px">{SVG["gamepad"].replace("28", "120")}</div>'
            if g.get('then', {}).get('icon') == 'gamepad' else '')
    html.append(f'<div id="{gid}-ph" class="phone" style="left:{px}px;top:12px;width:{pw}px;height:{ph}px"><div class="notch"></div>{"".join(cells)}{game}</div>')

    def banner(bid, b, icon=''):
        col = TONE.get(b.get('tone'), RED)
        small = f'<div class="bs">{b["small"]}</div>' if b.get('small') else ''
        ic = SVG['gamepad'].replace('28', '58') if icon == 'gamepad' else ''
        return (f'<div id="{bid}" class="bn" style="left:50%;top:150px;background:{col}">{small}'
                f'<div class="bm">{ic}<span>{b["text"]}</span></div></div>')
    html.append(banner(f'{gid}-b1', g['banner']))
    if g.get('then'):
        html.append(banner(f'{gid}-b2', g['then']['banner'], g['then'].get('icon')))
    hidden = [f'#{gid}-b1'] + ([f'#{gid}-b2', f'#{gid}-gm'] if g.get('then') else []) + [f'#{gid}-k{k}' for k in range(len(apps)) if g.get('locks')]
    tw.append(f"gsap.set({hidden!r},{{autoAlpha:0}});")
    tw.append(f"gsap.set(['#{gid}-b1','#{gid}-b2'],{{xPercent:-50,rotation:-7,transformPerspective:900}});")
    tw += [pop(f'#{gid}-a{k}', g['a'] + .15 + .09 * k) for k in range(len(apps))]
    t = g['banner']['t']
    tw += [f"tl.fromTo('#{gid}-b1',{{autoAlpha:0,scale:2.3,rotation:-18}},{{autoAlpha:1,scale:1,rotation:-7,duration:.3,ease:'back.out(1.5)',immediateRender:false}},{t - .04:.3f});",
           f"tl.fromTo('#{gid}-ph',{{x:-10}},{{x:0,duration:.4,ease:'elastic.out(1,0.3)',immediateRender:false}},{t + .2:.3f});"]
    tw += [pop(f'#{gid}-k{k}', t + .14 + .07 * k, .26) for k in range(len(apps)) if g.get('locks')]
    tw += show(gid, g['a'], g['b'])
    if g.get('then'):   # the banner flips: the phone comes back as it was, then turns over on the words
        th = g['then']
        tw += show(gid, th['a'], th['b'])
        f = th['t'] - .06
        tw += [f"tl.to('#{gid}-b1',{{rotationX:90,duration:.16,ease:'power2.in'}},{f:.3f});",
               f"tl.set('#{gid}-b1',{{autoAlpha:0}},{f + .16:.3f});",
               f"tl.fromTo('#{gid}-b2',{{autoAlpha:1,rotationX:-90}},{{autoAlpha:1,rotationX:0,duration:.26,ease:'back.out(1.6)',immediateRender:false}},{f + .16:.3f});",
               f"tl.to('#{gid}-ph',{{borderColor:'{GREEN}',boxShadow:'0 0 60px rgba(34,197,94,.55)',duration:.3}},{f + .16:.3f});",
               f"tl.to('#{gid}-ph .ti, #{gid}-ph .lk',{{autoAlpha:.22,duration:.25}},{f + .1:.3f});"]
        if th.get('icon') == 'gamepad':
            tw.append(pop(f'#{gid}-gm', f + .3, .4))
    return html, tw, ph + 30


def g_split(g):
    gid, html, tw = g['id'], [], []
    sides = g['sides'][:2]
    pw, gap, top, H = 440, 60, 0, 0
    cols = [TONE.get(sd.get('tone'), RED if n == 0 else GOLD) for n, sd in enumerate(sides)]        # badge colour
    labs = [TONE.get(sd.get('label_tone'), cols[n]) for n, sd in enumerate(sides)]                 # chip colour
    for n, sd in enumerate(sides):
        x, col = n * (pw + gap), cols[n]
        items = sd['items'][:6]
        size = 112 if len(items) <= 3 else 92
        per = min(3, max(1, len(items)))
        rows = -(-len(items) // per) if items else 0
        inner = [chip(f'{gid}-c{n}', sd['label'] or ('A' if n == 0 else 'B'), labs[n], 24, 22)]
        rows_ = [list(range(r * per, min(len(items), (r + 1) * per))) for r in range(rows)]
        while size > 64 and any(sum(tile_w(g['art'].get(items[k]), size) for k in row) + 26 * (len(row) - 1) > pw - 40 for row in rows_):
            size -= 8   # wide logos: shrink the row until it fits the panel
        for r, row in enumerate(rows_):
            ws = [tile_w(g['art'].get(items[k]), size) for k in row]
            ix, iy = (pw - sum(ws) - 26 * (len(row) - 1)) // 2, 92 + r * (size + 52)
            for k, w in zip(row, ws):
                inner.append(tile(f'{gid}-i{n}-{k}', items[k], g['art'].get(items[k]), size, True, ix, iy))
                if n == 0 and col == RED:
                    inner.append(f'<div id="{gid}-k{n}-{k}" class="lk" style="left:{ix + w - 22}px;top:{iy - 10}px">{SVG["lock"]}</div>')
                ix += w + 26
        by = 92 + rows * (size + 52) + 12
        if sd.get('badge'):
            if col == RED:
                inner.append(f'<div id="{gid}-bd{n}" class="stp" style="top:{by}px;color:{RED}">{sd["badge"]}</div>')
            else:
                inner.append(f'<div id="{gid}-bd{n}" class="wb" style="top:{by + 6}px;color:{col}">{SVG["warn"]}<span>{sd["badge"]}</span></div>')
        h = by + 92
        H = max(H, h)
        html.append(f'<div id="{gid}-p{n}" class="pn" style="left:{x}px;top:{top}px;width:{pw}px;height:{h}px">{"".join(inner)}</div>')
    if len(sides) == 2:
        html.append(f'<div id="{gid}-vs" class="vs" style="left:{pw + gap // 2 - 48}px;top:{H // 2 - 48}px">VS</div>')
    hid = [f'#{gid}-p{n}' for n in range(len(sides))] + [f'#{gid}-i{n}-{k}' for n, sd in enumerate(sides) for k in range(len(sd['items'][:6]))]
    hid += [f'#{gid}-k0-{k}' for k in range(len(sides[0]['items'][:6]))] if sides and cols[0] == RED else []
    hid += [f'#{gid}-bd{n}' for n, sd in enumerate(sides) if sd.get('badge')] + ([f'#{gid}-vs'] if len(sides) == 2 else [])
    tw.append(f"gsap.set({hid!r},{{autoAlpha:0}});")
    for n, sd in enumerate(sides):
        tw.append(f"tl.fromTo('#{gid}-p{n}',{{autoAlpha:0,y:26}},{{autoAlpha:1,y:0,duration:.4,ease:'power3.out',immediateRender:false}},{sd['t']:.3f});")
        tw += [pop(f'#{gid}-i{n}-{k}', t - .05) for k, t in enumerate(sd['beats'][:6])]
        if sd.get('badge'):
            col, bt = cols[n], sd['badge_t']
            if col == RED:
                tw.append(f"tl.fromTo('#{gid}-bd{n}',{{autoAlpha:0,scale:1.9,rotation:-12}},{{autoAlpha:1,scale:1,rotation:-4,duration:.28,ease:'back.out(1.4)',immediateRender:false}},{bt:.3f});")
                tw += [pop(f'#{gid}-k{n}-{k}', bt + .12 + .06 * k, .24) for k in range(len(sd['items'][:6])) if n == 0]
            else:
                tw.append(pop(f'#{gid}-bd{n}', bt, .3, 'scale:.6'))
                if sd.get('blink'):
                    reps = max(1, int((g['b'] - bt - .5) / .45))
                    reps -= reps % 2 == 0   # an odd repeat count ends on the lit state
                    tw.append(f"tl.fromTo('#{gid}-bd{n}',{{autoAlpha:1}},{{autoAlpha:.3,duration:.45,repeat:{reps},yoyo:true,ease:'sine.inOut',immediateRender:false}},{bt + .4:.3f});")
    if len(sides) == 2:
        tw.append(pop(f'#{gid}-vs', g['vs_t'] + .12, .36, 'scale:0'))
    tw += [f"tl.set('#{gid} .gi',{{autoAlpha:1}},{g['a']:.3f});"] + hide(f'#{gid} .gi', g['b'], at_cut(g['b']), .25)
    return html, tw, H


def g_flow(g):
    gid, html, tw = g['id'], [], []
    steps = g['steps'][:6]
    rh, gap, top0 = 70, 24, 84
    H = top0 + len(steps) * rh + (len(steps) - 1) * gap + 26
    inner = [chip(f'{gid}-t', g.get('title') or 'HOW IT HAPPENS', GOLD, None, 22, 'warn')]
    for k, st in enumerate(steps):
        y = top0 + k * (rh + gap)
        text = st['text']
        size = int(min(30, 690 / max(1e-6, text_width(text, 1, 'Inter-600-normal'))))
        inner.append(f'<div id="{gid}-r{k}" class="fr" style="top:{y}px"><div id="{gid}-n{k}" class="fn">{k + 1}</div>'
                     f'<div class="ft" style="font-size:{size}px">{text}</div></div>')
        if k:
            inner.append(f'<div class="fa" style="top:{y - gap + 2}px">'
                         f'<svg width="20" height="{gap - 4}" viewBox="0 0 20 20"><path d="M10 2v14M4 11l6 6 6-6" fill="none" stroke="rgba(255,255,255,.45)" '
                         f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')
    html.append(f'<div class="pn" style="left:0;top:0;width:{GFX_W}px;height:{H}px">{"".join(inner)}</div>')
    tw.append(f"gsap.set('#{gid} .fr',{{autoAlpha:.32}});")
    for k, st in enumerate(steps):
        col = RED if st.get('danger') else GOLD
        t = st['t'] - .06
        tw += [f"tl.to('#{gid}-r{k}',{{autoAlpha:1,borderColor:'{col}',backgroundColor:'rgba(255,255,255,.07)',duration:.2}},{t:.3f});",
               f"tl.to('#{gid}-n{k}',{{backgroundColor:'{col}',color:'#111',duration:.2}},{t:.3f});",
               f"tl.fromTo('#{gid}-r{k}',{{scale:1.045}},{{scale:1,duration:.35,ease:'power2.out',immediateRender:false}},{t:.3f});"]
        if k:
            tw += [f"tl.to('#{gid}-r{k - 1}',{{borderColor:'rgba(255,255,255,.18)',duration:.25}},{t:.3f});",
                   f"tl.to('#{gid}-n{k - 1}',{{backgroundColor:'#ffffff',color:'#111',duration:.25}},{t:.3f});"]
    tw += show(gid, g['a'], g['b'])
    return html, tw, H


def g_stat(g):
    gid, html, tw = g['id'], [], []
    val = g['value']
    size = int(min(176, 860 / max(1e-6, text_width(val, 1, 'InterTight-900-normal'))))
    digits = []
    for k, ch in enumerate(val):
        if ch.isdigit():
            col = ''.join(f'<span>{d % 10}</span>' for d in range(20))
            digits.append(f'<span class="dg"><span id="{gid}-d{k}" class="col">{col}</span></span>')
        else:
            digits.append(f'<span class="dc">{ch}</span>')
    y = 78
    inner = [chip(f'{gid}-s', g['source'], GOLD, None, 22)] if g.get('source') else []
    inner.append(f'<div class="num" style="top:{y}px;font-size:{size}px;height:{size}px">{"".join(digits)}</div>')
    y += round(size * 1.04)
    lab = g.get('label_text', '')
    if lab:
        ls = int(min(62, 860 / max(1e-6, text_width(lab, 1, 'InterTight-800-normal'))))
        inner.append(f'<div id="{gid}-l" class="sl" style="top:{y}px;font-size:{ls}px">{lab}</div>')
        y += round(ls * 1.2)
    if g.get('note'):
        inner.append(f'<div id="{gid}-n" class="sn" style="top:{y + 6}px">{g["note"]}</div>')
        y += 6 + 2 * 38
    H = y + 30
    html.append(f'<div class="pn" style="left:0;top:0;width:{GFX_W}px;height:{H}px">{"".join(inner)}</div>')
    t, a = g['t'], g['a']
    start = max(a + .3, t - 1.1)
    tw.append(f"gsap.set([{', '.join(repr(f'#{gid}-{x}') for x in ('l', 'n') if (x == 'l' and lab) or (x == 'n' and g.get('note')))}],{{autoAlpha:0}});")
    for k, ch in enumerate(val):   # every digit rolls a full turn and lands on its own value as the number is said
        if ch.isdigit():
            tw.append(f"tl.fromTo('#{gid}-d{k}',{{yPercent:0}},{{yPercent:{-(10 + int(ch)) * 5},duration:{t + .12 - start + .04 * k:.3f},"
                      f"ease:'power3.out',immediateRender:false}},{start:.3f});")
    if lab:
        tw.append(f"tl.fromTo('#{gid}-l',{{autoAlpha:0,y:18}},{{autoAlpha:1,y:0,duration:.35,ease:'power2.out',immediateRender:false}},{t + .2:.3f});")
    if g.get('note'):
        tw.append(f"tl.fromTo('#{gid}-n',{{autoAlpha:0,y:12}},{{autoAlpha:1,y:0,duration:.35,ease:'power2.out',immediateRender:false}},{t + .55:.3f});")
    tw += show(gid, a, g['b'])
    return html, tw, H


TOPO = None


def countries_geo():
    """{name: [polygon: [ring: [(lon, lat)]]]} from the bundled world map (Natural Earth 1:110m via world-atlas)"""
    global TOPO
    if TOPO is None:
        topo, TOPO = load('assets/map/countries-110m.json', {}), {}
        if not topo:
            return TOPO
        (sx, sy), (tx, ty) = topo['transform']['scale'], topo['transform']['translate']
        arcs = []
        for arc in topo['arcs']:
            x = y = 0
            pts = []
            for dx, dy in arc:
                x += dx; y += dy
                pts.append((x * sx + tx, y * sy + ty))
            arcs.append(pts)

        def ring(idx):
            pts = []
            for i in idx:
                a = arcs[i] if i >= 0 else arcs[~i][::-1]
                pts.extend(a if not pts else a[1:])
            return pts
        for geo in next(iter(topo['objects'].values()))['geometries']:
            polys = geo.get('arcs', []) if geo['type'] == 'MultiPolygon' else [geo.get('arcs', [])] if geo['type'] == 'Polygon' else []
            TOPO[geo['properties']['name']] = [[ring(r) for r in poly] for poly in polys]
    return TOPO


def g_map(g):
    gid, html, tw = g['id'], [], []
    geo = countries_geo()
    places = [p for p in g.get('places', []) if p in geo]
    H, mw, mh, mx, my = 470, 580, 422, 24, 24
    if not places:
        MISSING.append(f"{gid} map: none of {g.get('places')} is in the world map")
        return [], [], 0
    pts = [p for name in places for poly in geo[name] for p in poly[0]]
    lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    span = max((lon1 - lon0) * k * 1.3 / mw, (lat1 - lat0) * 1.3 / mh)   # degrees per pixel, 15% air each side
    def xy(lon, lat):
        return mx + mw / 2 + (lon - cx) * k / span, my + mh / 2 - (lat - cy) / span
    paths, ids = [], {}
    for name, polys in geo.items():
        d = []
        for poly in polys:
            for r in poly:
                if any(abs(a[0] - b[0]) > 180 for a, b in zip(r, r[1:])):
                    continue   # rings across the date line (Fiji, Russia's far east) are never in a regional map
                q = [xy(*p) for p in r]
                if max(x for x, _ in q) < mx - 40 or min(x for x, _ in q) > mx + mw + 40 or max(y for _, y in q) < my - 40 or min(y for _, y in q) > my + mh + 40:
                    continue
                d.append('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in q) + 'Z')
        if d:
            pid = f'{gid}-m{len(paths)}'
            if name in places:
                ids[name] = pid
            paths.append(f'<path id="{pid}" d="{"".join(d)}" class="{"mpl" if name in places else "mc"}"/>')
    # the place labels, the target tiles, and the lines between them
    inner, lines, cen = [], [], {}
    for n, name in enumerate(places):
        ring_ = max((poly[0] for poly in geo[name]), key=len)
        q = [xy(*p) for p in ring_]
        cen[name] = (sum(x for x, _ in q) / len(q), sum(y for _, y in q) / len(q))
        lx, ly = min(x for x, _ in q), min(y for _, y in q)
        inner.append(chip(f'{gid}-pl{n}', name, GOLD, round(max(mx + 8, min(lx, mx + mw - 200))), round(max(my + 8, min(ly - 46, my + mh - 50)))))
    targets = g.get('targets', [])[:3]
    ts = 96
    col_x = mx + mw + 50
    for n, tg in enumerate(targets):
        ty = round(H / 2 - (len(targets) * (ts + 40) - 40) / 2 + n * (ts + 40))
        tx = col_x + (GFX_W - col_x - min(tile_w(g['art'].get(tg), ts), GFX_W - col_x - 24) - 24) // 2
        inner.append(tile(f'{gid}-tg{n}', tg, g['art'].get(tg), ts, True, tx, ty))
        ex, ey = tx - 10, ty + ts / 2
        for m, name in enumerate(places):
            sx, sy = cen[name]
            c1x, c1y = (sx + ex) / 2, min(sy, ey) - 90
            lines.append(f'<path id="{gid}-ln{n}-{m}" d="M{sx:.1f},{sy:.1f} Q{c1x:.1f},{c1y:.1f} {ex:.1f},{ey:.1f}" pathLength="1" class="mln"/>')
    svg = (f'<svg class="msv" width="{GFX_W}" height="{H}" viewBox="0 0 {GFX_W} {H}"><defs><clipPath id="{gid}-clip">'
           f'<rect x="{mx}" y="{my}" width="{mw}" height="{mh}" rx="20"/></clipPath></defs>'
           f'<g clip-path="url(#{gid}-clip)"><rect x="{mx}" y="{my}" width="{mw}" height="{mh}" fill="#11151b"/>{"".join(paths)}</g>{"".join(lines)}</svg>')
    html.append(f'<div class="pn mp" style="left:0;top:0;width:{GFX_W}px;height:{H}px">{svg}{"".join(inner)}</div>')
    hid = [f'#{gid}-pl{n}' for n in range(len(places))] + [f'#{gid}-tg{n}' for n in range(len(targets))]
    tw.append(f"gsap.set({hid!r},{{autoAlpha:0}});")
    tw.append(f"gsap.set('#{gid} .mln',{{strokeDashoffset:1}});")
    for n, (name, t) in enumerate(zip(places, g.get('place_t', []))):
        tw += [f"tl.to('#{ids[name]}',{{fill:'{GOLD}',duration:.45,ease:'power2.out'}},{t - .05:.3f});", pop(f'#{gid}-pl{n}', t, .3, 'scale:.7')]
    for n, t in enumerate(g.get('target_t', [])[:3]):
        tw.append(pop(f'#{gid}-tg{n}', t - .08))
        tw += [f"tl.to('#{gid}-ln{n}-{m}',{{strokeDashoffset:0,duration:.6,ease:'power2.inOut'}},{t:.3f});" for m in range(len(places))]
    tw += show(gid, g['a'], g['b'])
    return html, tw, H


def g_custom(g):
    """a graphic no built-in kind draws: a transparent insert a sub-agent rendered (references/overlays.md)"""
    gid, f = g['id'], g.get('insert') or f"assets/graphics/{g['id']}.webm"
    if not os.path.isfile(f):
        MISSING.append(f"{gid} ({g['scene']}): {f} not built yet: \"{g['visual'][:90]}\"")
        return [], [], 0
    w, h = img_size(f)
    s = min(1.0, GFX_W / w, 560 / h)
    W, H = round(w * s), round(h * s)
    html = [f'<video id="{gid}-v" src="{f}" muted playsinline data-start="{g["a"]:.3f}" data-duration="{g["b"] - g["a"]:.3f}" '
            f'data-track-index="5" style="position:absolute;left:{(GFX_W - W) // 2}px;top:0;width:{W}px;height:{H}px"></video>']
    return html, show(gid, g['a'], g['b']), H


def graphics():
    html, tw = [], []
    for g in GFX:
        g.setdefault('art', {})
        maker = {'stamp': g_stamp, 'split': g_split, 'flow': g_flow, 'stat': g_stat, 'map': g_map}.get(g['kind'], g_custom)
        h, t, H = maker(g)
        if not h:
            continue
        end = g['then']['b'] if g.get('then') else g['b']
        head = min(head_at(seg_at(x), x) for x in [g['a'] + i * .25 for i in range(int((end - g['a']) / .25) + 1)])
        room = head - 30 - GFX_TOP
        sc = min(1.0, room / H) if H else 1.0
        if sc < .62:
            GFX_TIGHT.append(f"{g['id']} {g['kind']} {g['a']:.2f}-{end:.2f}: head top y {head:.0f}, scaled to {sc:.2f}: frame those shots wider")
        html.append(f'<div id="{g["id"]}" class="gfx" style="left:{GFX_X}px;top:{GFX_TOP}px;width:{GFX_W}px;height:{H}px;transform:scale({max(sc, .5):.3f})">'
                    f'<div class="gi">{"".join(h)}</div></div>')
        tw += [f"gsap.set('#{g['id']} .gi',{{autoAlpha:0}});"] + t
    return html, tw


# ------------------------------------------------------------------ cool girl extras: handwritten punch word, sparkles
SCRIPT_FONT, SCRIPT_LH = 'Caveat-600-normal', 1.0
POS = {}   # punch display text -> (top, size, front, font, a, b), filled by core()
BEHIND = []   # behind-head words for scripts/wordcheck.py: box, colour, resting window (work/reel.json "behind")


def behind_box(text, top, size, font, lh, col, rest_a, b):
    """where a behind-head word rests: render.py checks those frames for a word losing letters and draws them again"""
    w = text_width(text, size, font, PU['track'] if font != SCRIPT_FONT else 0, .04) * 1.06 + 24   # + the shot's push-in
    rest_b = b - (0 if at_cut(b) else .25)
    if rest_b - rest_a >= .2:
        BEHIND.append({'text': text, 'rest': [round(rest_a, 3), round(rest_b, 3)], 'colour': col,
                       'box': [round(540 - w / 2), round(top - .08 * size), round(540 + w / 2), round(top + size * lh * 1.12)]})


def script_k():
    m = METRICS[SCRIPT_FONT]
    return (SCRIPT_LH + m['ascent'] - m['descent']) / 2, m['x_height'], m['cap_height']


def script_behind_head(sid, a, b, text):
    """behind_head() with Caveat's own metrics"""
    k, xh, cap = script_k()
    hd = min(head_at(sid, a), head_at(sid, min(b, a + .6)))
    fit = SERIF_W / text_width(text, 1, SCRIPT_FONT, 0, .02)
    clear = (hd - top_limit(sid)) / (1.05 * cap - .2 * xh)
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
        if win and win['kind'] == 'split' or gfx_at(a, a + .6):   # the split's labels / a graphic say these words
            continue
        nxt = PUNCHES[k + 1][1] - .04 if k + 1 < len(PUNCHES) else DUR + 1   # the last word holds to the end
        b = min(END[sid], nxt - .02, a + 1.9) if END[sid] < DUR - .01 else min(nxt - .02, DUR)
        if win:   # over a cutaway: the word sits in front, under the card
            b = min(b, win['b'])
            size, top = under_card(text, it, win)
            front_html.append(punch_div(f's{k}', text, it, top, size, 'pw front'))
            POS[text] = (top, size, True, PU['font_it'] if it else PU['font'], a, b)
            tw += punch_in(f'#s{k}', a)
        elif text in SCRIPT_PUNCH:   # handwritten word behind the head, underline drawn under it
            top, size = script_behind_head(sid, a, b, text)
            back_html.append(script_div(f's{k}', text, top, size))
            POS[text] = (top, size, False, SCRIPT_FONT, a, b)
            tw += script_in(f'#s{k}', a, len(text))
            behind_box(text, top, size, SCRIPT_FONT, 1.0, '#FFF8EF', a + .032 * len(text) + .55, b)
        else:
            top, size = behind_head(sid, a, b, text, it)
            if size < SMALL * PU['size'][shot(sid)]:   # a high head in a close-up leaves no room: say so now, not after the render
                SMALL_WORDS.append(f"{sid} {text!r}: only {size}px behind the head (head top y {min(head_at(sid, a), head_at(sid, b)):.0f})")
            back_html.append(punch_div(f's{k}', text, it, top, size))
            POS[text] = (top, size, False, PU['font_it'] if it else PU['font'], a, b)
            tw += punch_in(f'#s{k}', a)
            behind_box(text, top, size, PU['font_it'] if it else PU['font'], PU['lh'], PU['color'],
                       a + {'mask': .6 + .028 * len(text), 'rise': .45}.get(PU['anim'], .3) + .1, b)
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
    for g in GFX:   # a graphic comes in on a soft whoosh; stamps, the VS disc and a landing number pop; steps click
        for t in [g['a']] + ([g['then']['a']] if g.get('then') else []):
            if all(abs(t - u) > .8 for u in used):
                out.append(('whoosh-short', t, .16)); used.append(t)
        if g['kind'] == 'stamp':
            out += [('pop', g['banner']['t'], .14)] + ([('pop', g['then']['t'], .14)] if g.get('then') else [])
        elif g['kind'] == 'split' and len(g.get('sides', [])) == 2:
            out.append(('pop', g['vs_t'] + .12, .12))
        elif g['kind'] == 'flow':
            out += [('click-soft', st['t'], .18) for st in g['steps']]
        elif g['kind'] == 'stat':
            out.append(('pop', g['t'] + .1, .14))
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
.card img.pz{{transform-origin:50% 50%}}
.pill{{position:absolute;left:18px;top:18px;padding:11px 18px 10px 22px;border-radius:999px;background:rgba(10,13,18,.74);
  color:{CREAM};font:500 24px Montserrat;letter-spacing:.28em;white-space:nowrap;transform-origin:0 50%}}
#endc{{position:absolute;inset:0;overflow:hidden;background:#0d1015}}
#endc .pw{{z-index:3}}

/* storyboard graphics: dark panels in the wall space above the head (VISUALS drawn, every element on its word) */
.gfx{{position:absolute;z-index:12;transform-origin:50% 0}}
.gfx .gi{{position:absolute;inset:0}}
.pn{{position:absolute;border-radius:30px;background:rgba(13,16,21,.9);border:1.5px solid rgba(255,255,255,.1);
  box-shadow:0 30px 80px rgba(0,0,0,.5),0 6px 18px rgba(0,0,0,.3)}}
.chip{{position:absolute;display:inline-flex;align-items:center;gap:10px;padding:9px 18px 8px;border-radius:999px;font:600 20px Montserrat;
  letter-spacing:.12em;white-space:nowrap;border:1.5px solid currentColor;background:rgba(0,0,0,.25)}}
.chip svg{{width:22px;height:22px}}
.ti{{position:absolute;display:flex;flex-direction:column;align-items:center;gap:10px}}
.tl{{display:flex;align-items:center;justify-content:center;overflow:hidden;flex:none;box-shadow:0 8px 22px rgba(0,0,0,.35)}}
.tl img{{display:block}}
.tn{{font:600 21px Inter;color:#d6dbe3;white-space:nowrap}}
.lk{{position:absolute;width:30px;height:30px;border-radius:50%;background:#EF4444;display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 3px #0d1015}}
.phone{{position:absolute;border-radius:44px;background:linear-gradient(180deg,#14171d,#0b0d11);border:3px solid #2c313a;
  box-shadow:0 30px 80px rgba(0,0,0,.55)}}
.phone .notch{{position:absolute;left:50%;top:14px;width:84px;height:24px;margin-left:-42px;border-radius:12px;background:#000}}
.phone .ph0{{position:absolute;border-radius:14px;background:rgba(255,255,255,.07)}}
.phone .gm{{position:absolute;color:#22C55E;filter:drop-shadow(0 0 22px rgba(34,197,94,.7))}}
.bn{{position:absolute;padding:12px 34px 16px;border-radius:14px;text-align:center;color:#fff;white-space:nowrap;
  box-shadow:0 18px 40px rgba(0,0,0,.45);transform-origin:50% 50%}}
.bn .bs{{font:600 19px Montserrat;letter-spacing:.32em;opacity:.92;margin-bottom:4px}}
.bn .bm{{display:flex;align-items:center;gap:16px;font:900 62px 'Inter Tight';letter-spacing:-.01em;line-height:1}}
.vs{{position:absolute;width:96px;height:96px;border-radius:50%;background:#F6D64A;color:#111;display:flex;align-items:center;
  justify-content:center;font:900 38px 'Inter Tight';box-shadow:0 0 0 6px rgba(13,16,21,.9),0 12px 30px rgba(0,0,0,.4);z-index:2}}
.stp{{position:absolute;left:50%;margin-left:-160px;width:320px;text-align:center;padding:10px 0 12px;border:4px solid currentColor;
  border-radius:14px;font:900 40px 'Inter Tight';line-height:1;letter-spacing:.01em}}
.wb{{position:absolute;left:50%;transform:translateX(-50%);display:inline-flex;align-items:center;gap:10px;padding:12px 20px;border-radius:999px;
  border:2px solid currentColor;background:rgba(246,214,74,.12);font:800 24px 'Inter Tight';letter-spacing:.06em;white-space:nowrap}}
.wb svg{{width:26px;height:26px}}
.fr{{position:absolute;left:60px;width:820px;height:70px;border-radius:18px;border:2px solid rgba(255,255,255,.18);background:rgba(255,255,255,.04);
  display:flex;align-items:center;gap:20px;padding:0 24px;transform-origin:50% 50%}}
.fn{{width:42px;height:42px;border-radius:50%;background:#ffffff;color:#111;font:800 22px 'Inter Tight';display:flex;align-items:center;
  justify-content:center;flex:none}}
.ft{{font-family:Inter;font-weight:600;color:#fff;white-space:nowrap}}
.fa{{position:absolute;left:50%;margin-left:-10px}}
.num{{position:absolute;left:0;right:0;text-align:center;font-family:'Inter Tight';font-weight:900;color:#F6D64A;line-height:1;
  letter-spacing:-.02em;white-space:nowrap}}
.num .dg{{display:inline-block;height:1em;overflow:hidden;vertical-align:top}}
.num .dg .col{{display:block}}
.num .dg .col span{{display:block;height:1em}}
.num .dc{{display:inline-block;vertical-align:top}}
.sl{{position:absolute;left:0;right:0;text-align:center;font-family:'Inter Tight';font-weight:800;color:#fff;line-height:1.1;white-space:nowrap}}
.sn{{position:absolute;left:60px;right:60px;text-align:center;font:600 28px/1.35 Inter;color:#b8bfcb}}
.mp{{overflow:hidden}}
.msv{{position:absolute;left:0;top:0}}
.msv .mc{{fill:#272c35;stroke:#3a404b;stroke-width:1}}
.msv .mpl{{fill:#353b46;stroke:#4a515d;stroke-width:1}}
.msv .mln{{fill:none;stroke:#F6D64A;stroke-width:3;stroke-linecap:round;stroke-dasharray:1}}
.ctp{{position:absolute;left:50%;transform:translateX(-50%);padding:16px 56px 18px;border-radius:999px;background:#F6D64A;color:#111;
  font:900 46px 'Inter Tight';white-space:nowrap;box-shadow:0 14px 40px rgba(246,214,74,.25)}}
.tap{{position:absolute;left:50%;margin-left:-40px;width:80px;height:80px;border-radius:50%;border:4px solid rgba(255,255,255,.9)}}
.ctn{{position:absolute;left:0;right:0;text-align:center;color:#fff;font-family:'Inter Tight';font-weight:900;line-height:1;letter-spacing:-.02em;
  white-space:nowrap}}
.ctt{{position:absolute;left:0;right:0;text-align:center;color:#b8bfcb;font:600 30px Montserrat;letter-spacing:.06em}}
.plate .pi{{display:inline-block;vertical-align:-6px;margin-right:.55em}}
.plate .pi svg{{display:block}}

/* storyboard SUPER lines: lower-third plates under the chin, clear of the icon column */
.lt{{position:absolute;left:0;right:0;top:1398px;z-index:12;text-align:center}}
.plate{{display:inline-block;padding:16px 26px 15px 32px;border-radius:999px;background:rgba(10,13,18,.62);
  border:1px solid rgba(247,244,238,.16);color:{CREAM};font:500 26px Montserrat;white-space:nowrap;box-shadow:0 12px 34px rgba(0,0,0,.35)}}
.plate .st{{display:inline-block;letter-spacing:.24em;transform-origin:50% 50%}}
.plate.words .st{{margin:0 .22em}}
.plate .st.y{{color:{YEL}}}
.plate.mc{{font-size:29px;font-weight:600}}
.plate.mc .st{{letter-spacing:.02em}}
.plate .ar{{display:inline-block;margin:0 .55em 0 .32em;color:{CREAM};vertical-align:2px}}
.plate .ar svg{{display:block}}
'''

GIRL_CSS = f'''
/* cool girl: warm room behind the pictures, serif italic plates and labels, sparkles, handwritten punch word */
.cbg{{background:#1b1411}}
.cbg.split{{background:radial-gradient(120% 80% at 50% 42%,#4a362c 0%,#261b16 55%,#150f0c 100%)}}
#endc{{background:#1b1411}}
.plate{{background:rgba(48,30,22,.52);border:1px solid rgba(255,248,239,.22);color:#FFF8EF;font:italic 400 50px 'Instrument Serif';
  padding:8px 34px 12px 34px;box-shadow:0 12px 34px rgba(40,20,10,.35)}}
.plate .st{{letter-spacing:0}}
.plate.words .st{{margin:0 .12em}}
.plate .ar{{vertical-align:8px}}
.pill{{font:italic 400 40px 'Instrument Serif';letter-spacing:0;padding:4px 22px 9px 22px;
  background:rgba(40,26,20,.72);color:#FFF8EF}}
.spark{{position:absolute;color:{YEL};line-height:1;text-shadow:0 0 18px rgba(250,230,122,.55);transform-origin:50% 50%}}
.pw.script{{font-family:'Caveat';font-weight:600;font-style:normal;line-height:1;letter-spacing:.02em;color:#FFF8EF;
  text-shadow:0 10px 34px rgba(60,30,20,.5)}}
.pw.script .ch{{display:inline-block}}
.pw.script .ul{{position:absolute;left:50%;overflow:visible;stroke-dasharray:1;filter:drop-shadow(0 4px 10px rgba(60,30,20,.4))}}
''' if L['fx'] == 'girl' else ''
CSS += GIRL_CSS
if BR:   # the brand's text boxes: SUPER plates, labels, the closing frame's button (white text)
    CSS += f'''
.plate{{background:{BR['box']};border:1px solid rgba(255,255,255,.16);color:{BR['text']};box-shadow:0 12px 34px rgba(0,0,0,.35)}}
.plate .st.y{{color:{BR['text']};font-weight:700}}
.plate .ar{{color:{BR['text']}}}
.pill{{background:{BR['box']};color:{BR['text']}}}
.ctp{{background:{BR['box']};color:{BR['text']};box-shadow:0 14px 40px rgba(0,0,0,.3)}}
'''

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
    g_html, g_tw = graphics()
    tweens = grades() + s_tw + f_tw + c_tw + p_tw + e_tw + g_tw
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
{nl.join(g_html)}
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
               'storyboard_missing': MISSING, 'behind': BEHIND,
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
        print(f"  ({t:.2f}, {' '.join(norm(WORDS[i]['text']) for i in idx)!r}, {text!r}, {it}),   # {WORDS[idx[0]]['seg']}")
    if L['fx'] == 'girl':
        print(f"SPARKLE {'(automatic)' if SPARKLE is None else ''}: {sparkle_picks()}   SCRIPT_PUNCH: {sorted(SCRIPT_PUNCH) or 'none'}")
    for c in CUTAWAYS:
        print(f"cutaway {c['id']:8s} {c['a']:6.2f}-{c['b']:6.2f}  " + (f"{c['w']}x{c['h']} at ({c['x']},{c['y']}) {c['image']}" if c['kind'] == 'card' else 'split'))
    for g in GFX:
        print(f"graphic  {g['id']:8s} {g['a']:6.2f}-{g['b']:6.2f}  {g['kind']}  {g['visual'][:70]}")
print(f"wrote {OUT}  look {LOOK}  reel {REEL_DUR:.3f}s (a-roll {DUR:.3f}s)  {len(CUTS)} cuts  {len(PUNCHES)} punch words"
      + (f"  {len(CUTAWAYS)} cutaways  {len(SUPERS)} supers{'  end card' if ENDC else ''}" if PLAN else ''))
if STRICT:
    print(f"storyboard text: {SB_TEXT[0]} of {SB_TEXT[1]} spoken words shown as its script writes them (the rest as the EDL "
          f"lines write them); supers, labels and graphic text as written")
    for _w in SWAPS:
        print(f"   caption follows the script: {_w}")
    for _i, _t, _text, _it in PUNCHES:
        _form = ' '.join(bare(WORDS[k]['shown']) for k in _i)
        if ' '.join(bare(x) for x in _text.split()) != _form and PU['case'] != 'upper':
            print(f"   PUNCH {_text!r} is not the script's form {_form!r}: on purpose?")
if GFX:
    print(f"graphics: {len(GFX)} from the storyboard's VISUALS (captions under the face while they own the top of the frame)")
for _w in GFX_TIGHT:
    print('TIGHT graphic (a high head): ' + _w)
if MISSING and not RANGE:
    print('STORYBOARD NOT ON SCREEN (render.py refuses until these are built):')
    for _w in MISSING:
        print('  ' + _w)
if not RANGE and SMALL_WORDS:
    print('SMALL behind-head words (a high head in a close-up): pick a word on a wider shot, or set it in front:')
    for _w in SMALL_WORDS:
        print('  ' + _w)
if not RANGE:
    _missing = [piece_file(a, b) for a, b in PIECES if not os.path.isfile(piece_file(a, b))]
    print(f"cutout: {sum(b - a for a, b in PIECES)} of {FRAMES} frames in {len(PIECES)} pieces"
          + (f"  ({len(_missing)} not cut out yet: run scripts/cutout.py before snapshots and the render)" if _missing else '  (all cut out)'))
