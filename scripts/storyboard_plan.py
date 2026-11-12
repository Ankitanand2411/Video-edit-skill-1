#!/usr/bin/env python3
"""Place a storyboard on the cut: <project>/storyboard.json + words.json + segments.json -> storyboard_plan.json.

Usage:  PY storyboard_plan.py <project_dir>

What it decides (a starting point: LOOK at every picture and adjust the plan before building):
  scenes     where each storyboard scene sits in the reel. Each scene's SCRIPT is aligned to the spoken words (the
             creator rarely reads it word for word); a boundary goes on the first cut after the last word matched to
             the previous scene (else on the first word matched to the next one).
  cutaways   each scene's picture as a card while the voice carries on, on the shot whose words best match the
             scene's VISUALS (the first visuals line counts double; ties go to the shot closest to 2.8s long).
             Never in the first 2s of the reel. A shot longer than 4s gets a 2.5-3.8s window around the matches.
             VISUALS that ask for a split screen + a SUPER "A vs. B" -> a 'split' with the previous scene's picture
             (A) on top and this scene's (B) below, while the speaker says A ... B.
  supers     SUPER "W1 -> W2 -> W3" whose words are spoken -> 'steps' (each lights up as it is said);
             any other SUPER (not the last scene's) -> a lower-third plate over the scene's last ~3s;
             the last scene's SUPER -> the end card lines (one line per sentence).
  end_card   the last scene's picture + its SUPER, held END_HOLD s after the last word; when the last scene's VISUALS
             describe a closing frame / CTA ("Follow School Advisor for more education news"), that is the end card
             and the SUPER becomes a plate.
  graphics   every VISUALS line that describes a graphic, not a picture (sbgraphics.py: stamp, split, flow, stat, map,
             custom), timed to the words that name what it shows: an icon pops as its platform is said, a flow step
             lights up on its words, a number rolls up as it is spoken, a country lights up as it is named.
  coverage   every VISUALS line of every scene and what carries it on screen. Nothing is dropped silently: a line
             no graphic kind fits is a 'custom' graphic, built as a transparent insert (assets/graphics/<id>.webm).
"""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbgraphics  # noqa: E402
import skillenv  # noqa: E402

END_HOLD = 3.0
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP = set('a an and the of to in on at by for with from as is it its it\'s be are was were this that these those i we you they he she '
           'my our your their his her me us them so but or if then than too very just can could would will about into over up down '
           'out not no yes all some any each every while when where what which who how before after because really actually even '
           'also one two maybe kind lot get got do does did have has had being been close-up cut shot scene'.split())


def norm(t):
    t = re.sub(r"[^\w']", '', t.lower().replace('-', ''))
    return re.sub(r'is(ation|ations|e|ed|es|ing)$', r'iz\1', t) if len(t) > 6 else t   # radicalisation = radicalization


SAME = {'kid': 'child', 'children': 'child', 'preschooler': 'child', 'toddler': 'child', 'pen': 'pencil', 'keyboard': 'typ',
        'type': 'typ', 'handwrit': 'writ', 'alphabet': 'letter', 'radicalization': 'extrem', 'radicalizations': 'extrem',
        'radicalized': 'extrem', 'radicalize': 'extrem', 'radical': 'extrem', 'radicals': 'extrem', 'extremist': 'extrem',
        'extremists': 'extrem', 'extremism': 'extrem', 'extremism\'s': 'extrem', 'ig': 'instagram', 'insta': 'instagram',
        'fb': 'facebook'}


def stem(w):
    """crude English stem so 'write' / 'writing' / 'written', 'kids' / 'child' and 'letters' / 'letter' meet"""
    w = norm(w)
    if w in SAME:
        return SAME[w]
    if len(w) > 3 and w.endswith('ies'):
        w = w[:-3] + 'y'
    elif len(w) > 3 and w.endswith('s') and not w.endswith('ss'):
        w = w[:-1]
    for suf in ('ing', 'ed', 'en'):
        if len(w) > 4 and w.endswith(suf):
            w = w[:-len(suf)]
            break
    if len(w) > 4 and w.endswith('e'):
        w = w[:-1]
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in 'aeiou':
        w = w[:-1]
    return SAME.get(w, w)


def keywords(text):
    return {stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", text) if norm(w) not in STOP and len(norm(w)) > 2}


def tokens(text):
    """a phrase's keywords in order (numbers kept: '100,000' -> '100000')"""
    out = []
    for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9',.\-]*", text):
        n = norm(w).replace(',', '').replace('.', '')
        if n and n not in STOP and (len(n) > 2 or n.isdigit()):
            out.append(n if n.isdigit() else stem(w))
    return out


def same(word, tok):
    n = norm(word['text']).replace(',', '')
    if tok.isdigit():
        d = re.sub(r'\D', '', word['text'])
        return bool(d) and (tok.startswith(d) and len(d) >= min(3, len(tok)) or d == tok)
    return stem(word['text']) == tok


def find(words, phrase, lo, hi, after=-1, single=True):
    """index of the first spoken word in [lo, hi) after index `after` that starts `phrase`: its keywords in order, at
    most 2 other words between two of them. single=True falls back to the phrase's longest keyword on its own."""
    toks = tokens(phrase)
    if not toks:
        return None
    cand = [i for i, w in enumerate(words) if i > after and lo - .01 <= w['start'] < hi]
    for i in cand:
        if not same(words[i], toks[0]):
            continue
        j, ok = i, True
        for t in toks[1:]:
            nxt = next((k for k in range(j + 1, min(j + 4, len(words))) if same(words[k], t)), None)
            if nxt is None:
                ok = False; break
            j = nxt
        if ok:
            return i
    if single:   # the first place any one of its keywords is said ("Radicalisation / Exploitation" on "extremist")
        keys = [t for t in set(toks) if len(t) >= 4 or t.isdigit()]
        return next((i for i in cand if any(same(words[i], t) for t in keys)), None)
    return None


def sentence_end(words, i):
    """end time of the sentence word i is in (its first word ending in . ? ! at or after i)"""
    for k in range(i, len(words)):
        if words[k]['text'].rstrip()[-1:] in '.?!':
            return words[k]['end']
    return words[-1]['end']


def map_names():
    """country names in the template's world map (assets/map/countries-110m.json)"""
    f = os.path.join(SKILL, 'assets', 'template', 'assets', 'map', 'countries-110m.json')
    try:
        with open(f, encoding='utf-8') as fh:
            topo = json.load(fh)
        return sorted({g['properties']['name'] for g in next(iter(topo['objects'].values()))['geometries']}, key=len, reverse=True)
    except (OSError, ValueError, KeyError):
        return []


def picture_for(name, folder):
    """{'logo': file, 'photo': file} from the folder pictures whose names include this entity"""
    out, key = {}, name.lower().replace(' ', '')
    for f in folder:
        if key in [n.lower().replace(' ', '') for n in f.get('names', [])]:
            out.setdefault(f.get('kind', 'photo'), f['file'])
    return out


def plan_graphics(sb, words, scenes):
    """VISUALS graphics, timed: [{id, scene, kind, a, b, ...beats}], plus the coverage list"""
    names, folder = map_names(), sb.get('folder_images', [])
    fnames = sorted({n for f in folder for n in f.get('names', [])})
    out, coverage, used = [], [], set()
    for k, sc in enumerate(sb['scenes']):
        a0, b0 = scenes[k]['start'], scenes[k]['end']
        lo, hi = max(0.0, a0 - 1.0), b0 + 1.0
        rows = []
        for g in sbgraphics.graphics(sc.get('visuals', []), names, fnames):
            g['scene'] = sc['scene']
            if g['kind'] == 'shot':
                coverage.append({'scene': sc['scene'], 'visual': g['visual'],
                                 'as': 'the scene picture (footage described)' if sc.get('images') else
                                 'FOOTAGE NOT IN THE FOLDER: tell the user (b-roll / a picture for this scene)'})
                continue
            if g['kind'] == 'cta':
                rows.append(g); continue
            if sc.get('images') and g['kind'] == 'custom':   # a scene picture carries a line that is not a known graphic
                coverage.append({'scene': sc['scene'], 'visual': g['visual'], 'as': 'the scene picture (cutaway card)'})
                continue
            g['id'] = f'g{len(out) + 1}'

            def hit(phrase, after_i=-1, single=True):
                i = find(words, phrase, lo, hi, after_i, single)
                return (i, words[i]['start']) if i is not None else (None, None)
            if g['kind'] == 'stamp':
                i, t = hit(g['banner']['text'] or 'restricted')
                if not g['banner']['small']:   # "Under 16" from the scene's SUPER / script reads well above the banner
                    m = re.search(r'\b(under|over|aged?|below|above)\s+\d+\+?', sc.get('super', '') + ' ' + sc.get('script', ''), re.I)
                    g['banner']['small'] = m.group(0).upper() if m else ''
                g['a'] = round(max(a0, lo) + .15 if k == 0 else (t - 1.4 if t else a0), 3)
                g['banner']['t'] = round(t if t else g['a'] + 1.0, 3)
                g['b'] = round(min(b0, sentence_end(words, i) + .6 if i is not None else g['a'] + 3.5), 3)
                for app in g['apps']:
                    used.add(app.lower())
                if g.get('then'):
                    j, t2 = hit(g['then']['say'] or g['then']['banner']['text'], i if i is not None else -1)
                    if t2:
                        g['then'].update(t=round(t2, 3), a=round(max(g['b'] + .3, t2 - 1.8), 3),
                                         b=round(min(b0 + .6, sentence_end(words, j) + 1.0), 3))
                    else:
                        g['then'].update(t=round(g['b'] + 1.5, 3), a=round(g['b'] + .2, 3), b=round(g['b'] + 3.2, 3))
            elif g['kind'] == 'split':
                last = -1
                for side in g['sides']:
                    side['beats'] = []
                    for it in side['items']:
                        i, t = hit(it, last)
                        if i is None:
                            i, t = hit(it)
                        side['beats'].append(round(t, 3) if t is not None else None)
                        if i is not None:
                            last = max(last, i)
                        used.add(it.lower())
                ts = [t for s in g['sides'] for t in s['beats'] if t is not None]
                if not ts:
                    ts = [a0 + 1.0]
                left = [t for t in g['sides'][0]['beats'] if t is not None] if g['sides'] else []
                right = [t for t in g['sides'][1]['beats'] if t is not None] if len(g['sides']) > 1 else []
                g['a'] = round(max(lo, (left or ts)[0] - .8), 3)
                for n, side in enumerate(g['sides']):   # items nobody names appear with their panel
                    t0 = g['a'] + .25 if n == 0 else ((right or [ts[-1]])[0] - .9)
                    side['t'] = round(max(g['a'], t0), 3)
                    side['beats'] = [round(t if t is not None else side['t'] + .3 + .25 * q, 3) for q, t in enumerate(side['beats'])]
                    side['badge_t'] = round(max(side['beats'] or [side['t']]) + .55, 3)
                g['vs_t'] = round(g['sides'][-1]['t'], 3)
                li = max(i for i, w in enumerate(words) if w['start'] <= max(ts) + .01)
                g['b'] = round(min(hi, max(sentence_end(words, li) + .7, g['a'] + 3.0)), 3)
            elif g['kind'] == 'flow':
                prev, times = -1, []
                for st in g['steps']:
                    i, t = hit(st['text'], prev)
                    times.append(t)
                    if i is not None:
                        prev = i
                known = [t for t in times if t is not None]
                start = known[0] if known else a0 + 1.0
                for q, t in enumerate(times):   # a step nobody says lights up between its neighbours
                    if t is None:
                        before = next((times[p] for p in range(q - 1, -1, -1) if times[p] is not None), start - 1.0)
                        after_t = next((times[p] for p in range(q + 1, len(times)) if times[p] is not None), None)
                        times[q] = (before + after_t) / 2 if after_t else before + 2.0
                for st, t in zip(g['steps'], times):
                    st['t'] = round(t, 3)
                g['a'] = round(max(lo, start - 2.5), 3)
                li = max(i for i, w in enumerate(words) if w['start'] <= times[-1] + .01)
                g['b'] = round(min(hi, sentence_end(words, li) + .8), 3)
                m = re.search(r'\b(they|he|she|it|we|you) (?:do|did|does) (?:it|this|that) by\b', ' '.join(w['text'] for w in words
                              if g['a'] <= w['start'] <= g['b']), re.I)
                g['title'] = g['title'] or (f"HOW {m.group(1).upper()} DO IT" if m and m.group(1).lower() in ('they', 'we', 'you')
                                            else 'HOW IT HAPPENS')
            elif g['kind'] == 'stat':
                i, t = hit(g['value'], single=False)
                if i is None:
                    i, t = hit(g['value'] + ' ' + g['label_text'])
                t = t if t is not None else a0 + 1.5
                src = g['source'].split()[0] if g['source'] else ''
                j, ts = hit(src, single=True) if src else (None, None)
                g['t'] = round(t, 3)
                g['a'] = round(max(lo, ts - .3 if ts is not None and 0 < t - ts < 6 else t - 1.2), 3)
                if g['source'] and not re.search(r'\d{4}', g['source']):   # "UNICEF study in 2022": the year on the chip
                    yr = re.search(r'\b(19|20)\d{2}\b', ' '.join(w['text'] for w in words if g['a'] - .5 <= w['start'] <= t + .5))
                    if yr:
                        g['source'] = f"{g['source']} · {yr.group(0)}"
                ii = i if i is not None else max(q for q, w in enumerate(words) if w['start'] <= t + .01)
                g['b'] = round(min(hi, sentence_end(words, ii) + .7), 3)
            elif g['kind'] == 'map':
                g['place_t'], g['target_t'], last = [], [], -1
                for pl in g['places']:
                    i, t = hit(pl, single=True)
                    g['place_t'].append(round(t, 3) if t is not None else None)
                for tg in g['targets']:
                    i, t = hit(tg, last)
                    g['target_t'].append(round(t, 3) if t is not None else None)
                    if i is not None:
                        last = i
                    used.add(tg.lower())
                ts = [t for t in g['place_t'] + g['target_t'] if t is not None] or [a0 + 1.0]
                g['a'] = round(max(lo, min(ts) - .3), 3)
                g['place_t'] = [t if t is not None else g['a'] + .4 for t in g['place_t']]
                g['target_t'] = [t if t is not None else max(g['place_t'] or [g['a']]) + .8 + .5 * q for q, t in enumerate(g['target_t'])]
                li = max(i for i, w in enumerate(words) if w['start'] <= max(ts) + .01)
                g['b'] = round(min(hi, sentence_end(words, li) + .7), 3)
            else:   # custom: the scene's span; built by hand as a transparent insert
                g['a'], g['b'] = round(a0 + .3, 3), round(min(b0, a0 + 4.5), 3)
                g['insert'] = f"assets/graphics/{g['id']}.webm"
            rows.append(g)
            out.append(g)
        for g in rows:
            coverage.append({'scene': sc['scene'], 'visual': g['visual'],
                             'as': 'end card (closing frame)' if g['kind'] == 'cta' else
                             f"graphic {g['id']} ({g['kind']}{': build ' + g['insert'] if g['kind'] == 'custom' else ''})"})
            if g.get('then'):
                coverage.append({'scene': sc['scene'], 'visual': g['then']['visual'], 'as': f"graphic {g['id']}: banner flip"})
    out.sort(key=lambda g: g['a'])
    for g, nxt in zip(out, out[1:]):   # one graphic at a time
        end = g['then']['b'] if g.get('then') else g['b']
        if end > nxt['a'] - .15:
            if g.get('then'):
                g['then']['b'] = round(max(g['then']['a'] + 1.5, nxt['a'] - .15), 3)
            else:
                g['b'] = round(max(g['a'] + 1.5, nxt['a'] - .15), 3)
    for g in out:   # the entities each graphic shows: an icon in the template, or a folder picture
        ents = (g.get('apps', []) + [i for s in g.get('sides', []) for i in s['items']] + g.get('targets', []))
        g['art'] = {e: {'icon': (sbgraphics.PLATFORMS.get(e) or (None,))[0], **picture_for(e, folder)} for e in ents}
    unused = [f['file'] for f in folder if not any(n.lower() in used for n in f.get('names', []))]
    return out, coverage, unused


def main():
    skillenv.utf8_stdio()
    proj = skillenv.path_arg(sys.argv[1])
    load = lambda f: json.load(open(os.path.join(proj, f), encoding='utf-8'))
    sb, words, segs = load('storyboard.json'), load('words.json'), load('segments.json')
    cut_t = [s['frame'] / 30 for s in segs]
    seg_end = {s['id']: (s['frame'] + s['frames']) / 30 for s in segs}
    seg_start = {s['id']: s['frame'] / 30 for s in segs}
    reel_end = seg_end[segs[-1]['id']]
    for w in words:
        w.setdefault('seg', max((s for s in segs if s['frame'] / 30 <= w['start'] + .02), key=lambda s: s['frame'])['id'])

    # 1. align every scene's script to the spoken words
    sb_tok, sb_scene = [], []
    for k, sc in enumerate(sb['scenes']):
        for t in re.findall(r"[\w'\-]+", sc['script']):
            if norm(t):
                sb_tok.append(norm(t)); sb_scene.append(k)
    sp_tok = [norm(w['text']) for w in words]
    match = {}   # spoken index -> scene
    for blk in difflib.SequenceMatcher(None, sb_tok, sp_tok, autojunk=False).get_matching_blocks():
        for i in range(blk.size):
            match[blk.b + i] = sb_scene[blk.a + i]
    n = len(sb['scenes'])
    first = {k: min((i for i, s in match.items() if s == k), default=None) for k in range(n)}
    last = {k: max((i for i, s in match.items() if s == k), default=None) for k in range(n)}
    bounds = [0.0]
    for k in range(1, n):
        prev = max((last[j] for j in range(k) if last[j] is not None), default=None)
        nxt = first[k]
        lo = words[prev]['end'] if prev is not None else bounds[-1]
        hi = words[nxt]['start'] if nxt is not None else lo
        cuts = [c for c in cut_t if lo - .05 <= c <= hi + .05 and c > bounds[-1]]
        bounds.append(cuts[0] if cuts else max(bounds[-1], hi - .05))
    bounds.append(reel_end)
    scenes = [{'scene': sc['scene'], 'start': round(bounds[k], 3), 'end': round(bounds[k + 1], 3),
               'matched_words': sum(1 for s in match.values() if s == k)} for k, sc in enumerate(sb['scenes'])]

    # 2. graphics (VISUALS that describe a graphic), cutaways, supers, end card
    graphics, coverage, unused = plan_graphics(sb, words, scenes)
    cutaways, supers, end_card = [], [], None
    last_word_t = max(w['start'] for w in words)
    for k, sc in enumerate(sb['scenes']):
        a0, b0 = scenes[k]['start'], scenes[k]['end']
        img = sc['images'][0]['file'] if sc['images'] else None
        sup, icon = sbgraphics.super_parts(sc['super'].strip())
        in_scene = [i for i, w in enumerate(words) if a0 - .01 <= w['start'] < b0 - .01]
        is_last = k == n - 1
        cta = next((g for g in sbgraphics.graphics(sc.get('visuals', []), [], []) if g['kind'] == 'cta'), None)
        if is_last:   # end card: last picture + SUPER (or the closing frame's CTA), after the last word lands
            if img or sup or cta:
                t_in = round(last_word_t + .8, 3)
                lines = [] if cta else [l.strip() for l in re.findall(r'[^.!?]+[.!?]?', sup) if l.strip()]
                end_card = {'scene': sc['scene'], 'image': img, 'in': t_in, 'hold': END_HOLD, 'lines': lines,
                            'cta': cta['cta'] if cta else None}
            if not cta or not sup:
                continue
        vis = ' '.join(sc['visuals'])
        split = re.search(r'split', vis, re.I) and re.search(r'\bvs\.?\b', sup, re.I)
        if split and img and k > 0 and sb['scenes'][k - 1]['images']:
            labels = [p.strip(' .').upper() for p in re.split(r'\bvs\.?', sup, flags=re.I)]
            hits = []
            for lab in labels:
                key = stem(lab.split()[0])
                hits.append(next((i for i in in_scene if stem(words[i]['text']) == key), None))
            if all(h is not None for h in hits):
                t1, t2 = words[hits[0]]['start'], words[hits[1]]['start']
                a = max(a0, t1 - .95)
                b = min(b0 + 1.2, max(words[hits[1]]['end'] + 1.1, a + 3.2))
                cutaways.append({'id': f'split{k + 1}', 'kind': 'split', 'scene': sc['scene'],
                                 'images': [sb['scenes'][k - 1]['images'][0]['file'], img], 'labels': labels,
                                 'a': round(a, 3), 'b': round(b, 3), 'label_t': [round(t1 - .07, 3), round(t2 - .07, 3)],
                                 'vs_t': round((t1 + t2) / 2, 3), 'bottom_t': round(t2 - .17, 3),
                                 'why': f'split screen: "{sup}" while the speaker says {labels[0].lower()} ... {labels[1].lower()}'})
                sup = ''   # the split's labels carry this SUPER
        elif img:
            kw_main, kw_all = keywords(sc['visuals'][0] if sc['visuals'] else ''), keywords(vis)
            best = None
            for s in segs:
                sa, se = s['frame'] / 30, seg_end[s['id']]
                if sa < a0 - .01 or se > b0 + .01 or se - max(sa, 2.0) < 1.5:
                    continue
                ws = [i for i in in_scene if words[i]['seg'] == s['id']]
                hit = [i for i in ws if stem(words[i]['text']) in kw_all]
                score = sum(2 if stem(words[i]['text']) in kw_main else 1 for i in hit)
                key = (score, -abs((se - sa) - 2.8))
                if best is None or key > best[0]:
                    best = (key, s, hit)
            if best:
                (score, _), s, hit = best
                sa, se = max(seg_start[s['id']], 2.0), seg_end[s['id']]
                if se - sa > 4.0 and hit:   # long shot: a window around the matching words
                    c = (words[hit[0]]['start'] + words[hit[-1]]['end']) / 2
                    sa, se = max(sa, c - 1.9), min(se, c + 1.9)
                elif se - sa > 4.0:
                    sa = se - 3.2
                shot_a, shot_b = max(seg_start[s['id']], 2.0), seg_end[s['id']]
                if shot_b - se < 1.0:   # no half-second flash of the speaker at either end: snap to the cut
                    se = shot_b
                if sa - shot_a < 1.0:
                    sa = shot_a
                if se - sa > 4.5:
                    sa = se - 4.5
                cutaways.append({'id': f'card{k + 1}', 'kind': 'card', 'scene': sc['scene'], 'image': img,
                                 'a': round(sa, 3), 'b': round(se, 3),
                                 'why': f"shot {s['id']}: " + (', '.join(words[i]['text'] for i in hit) if hit else 'no keyword match, closest length')})
        if sup:
            steps = [p.strip() for p in re.split(r'\s*(?:→|->|>)\s*', sup) if p.strip()]
            if len(steps) > 1:
                times, j = [], 0
                for st in steps:
                    key = stem(st)
                    i = next((i for i in in_scene if i >= j and stem(words[i]['text']) == key), None)
                    times.append(words[i]['start'] if i is not None else None); j = (i or j) + 1
                if all(t is not None for t in times):
                    sa = max(c for c in cut_t if c <= times[0] + .01)
                    sb_ = min((c for c in cut_t if c > times[-1]), default=b0)
                    supers.append({'id': f'steps{k + 1}', 'kind': 'steps', 'scene': sc['scene'], 'a': round(sa, 3), 'b': round(min(sb_, b0), 3),
                                   'steps': [[round(t, 3), st.upper()] for t, st in zip(times, steps)]})
                    continue
            # a plate goes up where its words are said ("POLICE WARNING" on "police chief warned"), else over the
            # scene's last ~3s; the last scene's plate (its closing frame is the end card) ends where the end card comes in
            end_b = min(b0, end_card['in']) if is_last and end_card else b0
            i = find(words, sup, a0 - .3, end_b, single=False)
            if i is None:
                rare = [t for t in tokens(sup) if len(t) >= 4 and sum(same(w, t) for w in words) == 1]
                i = next((find(words, t, a0 - .3, end_b) for t in rare if find(words, t, a0 - .3, end_b) is not None), None)
            if i is not None and words[i]['start'] + 2.5 <= end_b + .01:
                sa = max(a0, words[i]['start'] - .3)
                sb_ = min(end_b, sa + 3.4)
            else:
                sa, sb_ = max(a0, end_b - 3.1), end_b
            near = [c for c in cut_t if abs(c - sa) < .3]
            supers.append({'id': f'plate{k + 1}', 'kind': 'plate', 'scene': sc['scene'], 'a': round(near[0] if near else sa, 3),
                           'b': round(sb_, 3), 'text': sup.upper(), 'icon': icon, 'yellow_last': 2})
    for c in cutaways:   # a picture card covers the whole frame: never over a graphic
        for g in graphics:
            if c['a'] < (g['then']['b'] if g.get('then') else g['b']) and g['a'] < c['b']:
                print(f"NOTE cutaway {c['id']} {c['a']:.2f}-{c['b']:.2f} overlaps graphic {g['id']} {g['a']:.2f}-{g['b']:.2f}: move one")
    plan = {'scenes': scenes, 'graphics': graphics, 'cutaways': cutaways, 'supers': supers, 'end_card': end_card, 'coverage': coverage,
            'mood': sb.get('mood', ''), 'reel_end': round((end_card['in'] + end_card['hold']) if end_card else reel_end, 3)}
    with open(os.path.join(proj, 'storyboard_plan.json'), 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    for s in scenes:
        print(f"scene {s['scene']:10s} {s['start']:6.2f}-{s['end']:6.2f}  ({s['matched_words']} script words matched)")
    for c in cutaways:
        print(f"cutaway {c['kind']:5s} {c['a']:6.2f}-{c['b']:6.2f}  {c['scene']:10s} {c['why']}")
    for s in supers:
        print(f"super {s['kind']:5s} {s['a']:6.2f}-{s['b']:6.2f}  " + (' > '.join(f'{w}@{t:.2f}' for t, w in s['steps']) if s['kind'] == 'steps' else s['text']))
    for g in graphics:
        extra = {'stamp': lambda: f"{', '.join(g['apps'])} | {g['banner']['text']}@{g['banner']['t']:.2f}"
                                  + (f" -> {g['then']['banner']['text']}@{g['then']['t']:.2f} ({g['then']['a']:.2f}-{g['then']['b']:.2f})" if g.get('then') else ''),
                 'split': lambda: ' VS '.join(f"{s['label']}[{', '.join(f'{i}@{t:.2f}' for i, t in zip(s['items'], s['beats']))}]" for s in g['sides']),
                 'flow': lambda: f"{g['title']}: " + ' > '.join(f"{s['text']}@{s['t']:.2f}" for s in g['steps']),
                 'stat': lambda: f"{g['value']} {g['label_text']}@{g['t']:.2f} ({g['source']})",
                 'map': lambda: ', '.join(f'{p}@{t:.2f}' for p, t in zip(g['places'], g['place_t'])) + ' -> '
                                + ', '.join(f'{p}@{t:.2f}' for p, t in zip(g['targets'], g['target_t'])),
                 'custom': lambda: f"BUILD {g['insert']}: {g['visual'][:70]}"}.get(g['kind'], lambda: '')()
        print(f"graphic {g['id']:3s} {g['kind']:6s} {g['a']:6.2f}-{g['b']:6.2f}  {g['scene']:8s} {extra}")
        for e, art in g.get('art', {}).items():
            if not art.get('icon') and not art.get('logo') and not art.get('photo'):
                print(f"   no picture for {e!r}: drop its logo next to the storyboard (named '{e.lower()} logo') or name a folder picture")
    if end_card:
        print(f"end card {end_card['in']:.2f} +{end_card['hold']}s  {end_card['image']}  "
              + (f"CTA {end_card['cta']}" if end_card.get('cta') else ' / '.join(end_card['lines'])))
    print('storyboard coverage (every VISUALS line and what carries it):')
    for c in coverage:
        print(f"   {c['scene']:8s} {c['as']:34s} {c['visual'][:80]}")
    for f in unused:
        print(f"folder picture not used by any graphic: {f} (look at it: name it in storyboard.json, or leave it out)")


if __name__ == '__main__':
    main()
