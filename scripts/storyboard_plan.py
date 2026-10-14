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
  end_card   the last scene's picture + its SUPER, held END_HOLD s after the last word.
"""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

END_HOLD = 3.0
STOP = set('a an and the of to in on at by for with from as is it its it\'s be are was were this that these those i we you they he she '
           'my our your their his her me us them so but or if then than too very just can could would will about into over up down '
           'out not no yes all some any each every while when where what which who how before after because really actually even '
           'also one two maybe kind lot get got do does did have has had being been close-up cut shot scene'.split())


def norm(t):
    return re.sub(r"[^\w']", '', t.lower().replace('-', ''))


SAME = {'kid': 'child', 'children': 'child', 'preschooler': 'child', 'toddler': 'child', 'pen': 'pencil', 'keyboard': 'typ',
        'type': 'typ', 'handwrit': 'writ', 'alphabet': 'letter'}


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

    # 2. cutaways, supers, end card
    cutaways, supers, end_card = [], [], None
    last_word_t = max(w['start'] for w in words)
    for k, sc in enumerate(sb['scenes']):
        a0, b0 = scenes[k]['start'], scenes[k]['end']
        img = sc['images'][0]['file'] if sc['images'] else None
        sup = sc['super'].strip()
        in_scene = [i for i, w in enumerate(words) if a0 - .01 <= w['start'] < b0 - .01]
        is_last = k == n - 1
        if is_last:   # end card: last picture + SUPER, after the last word lands
            if img or sup:
                t_in = round(last_word_t + .8, 3)
                lines = [l.strip() for l in re.findall(r'[^.!?]+[.!?]?', sup) if l.strip()]
                end_card = {'scene': sc['scene'], 'image': img, 'in': t_in, 'hold': END_HOLD, 'lines': lines}
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
            sa = max(a0, b0 - 3.1)
            near = [c for c in cut_t if abs(c - sa) < .8]
            supers.append({'id': f'plate{k + 1}', 'kind': 'plate', 'scene': sc['scene'], 'a': round(near[0] if near else sa, 3),
                           'b': round(b0, 3), 'text': sup.upper(), 'yellow_last': 2})
    plan = {'scenes': scenes, 'cutaways': cutaways, 'supers': supers, 'end_card': end_card,
            'mood': sb.get('mood', ''), 'reel_end': round((end_card['in'] + end_card['hold']) if end_card else reel_end, 3)}
    with open(os.path.join(proj, 'storyboard_plan.json'), 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    for s in scenes:
        print(f"scene {s['scene']:10s} {s['start']:6.2f}-{s['end']:6.2f}  ({s['matched_words']} script words matched)")
    for c in cutaways:
        print(f"cutaway {c['kind']:5s} {c['a']:6.2f}-{c['b']:6.2f}  {c['scene']:10s} {c['why']}")
    for s in supers:
        print(f"super {s['kind']:5s} {s['a']:6.2f}-{s['b']:6.2f}  " + (' > '.join(f'{w}@{t:.2f}' for t, w in s['steps']) if s['kind'] == 'steps' else s['text']))
    if end_card:
        print(f"end card {end_card['in']:.2f} +{end_card['hold']}s  {end_card['image']}  {' / '.join(end_card['lines'])}")


if __name__ == '__main__':
    main()
