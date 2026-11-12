#!/usr/bin/env python3
"""Storyboard VISUALS -> the graphics to build (no timing here: storyboard_plan.py times them against the speech).

A storyboard row often has no picture at all: its VISUALS describe graphics ("Animated Overlay: a smartphone with
locked TikTok / IG / Facebook icons and a red RESTRICTED banner", "Split-Screen Graphic: Left Side (Banned) ... Right
Side (Allowed) ...", "Flowchart Infographic: A -> B -> C", "Stat Callout Card: "100,000 Malaysian Kids"", "Interactive
Map Graphic: Australia and Malaysia ...", "Closing Frame: Follow School Advisor for more education news - CTA").
The first reel built from such a storyboard ignored every one of them (it only knew pictures); these are what the
viewer was meant to see, so each one becomes a graphic. The template draws these kinds (build.py, graphics layer):

  stamp   a phone (or a panel) of app icons with a stamp banner slammed across it; a following "Transition" line
          flips the banner (RESTRICTED -> UNRESTRICTED, a gaming controller...)
  split   two panels side by side (Left / Right, Banned / Allowed, A vs. B): each side's icons pop in as they are
          named, its badge stamps on, a VS disc between
  flow    a numbered list of steps that light up one by one as they are said (A -> B -> C)
  stat    a big number that rolls up as it is said, its label and note, the source on a chip
  map     the named countries drawn from a world map, lighting up as they are named, lines out to the named platforms
  cta     the closing frame: verb pill (Follow), name, tagline (the end card)
  shot    footage or a camera direction (close-up of a child..., b-roll of ...): no graphic. In a scene with its own
          picture the picture carries it; without one it is footage the folder does not have: tell the user
  custom  any other graphic: built as a transparent insert (references/overlays.md), assets/graphics/<id>.webm

Standard library only.
"""
import re

ARROWS = r'\s*(?:➔|→|->|⇒|➜|➡|⟶|=>|>)\s*'
QUOTE = re.compile(r'["“”]([^"“”]{1,80})["“”]')
EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿️‍\U0001F1E6-\U0001F1FF⬀-⯿]')

# platforms the template has an icon for (assets/icons/<slug>.svg: Simple Icons, CC0), or a name a folder image covers
PLATFORMS = {
    'TikTok': ('tiktok', ('tiktok', 'tik tok')), 'Instagram': ('instagram', ('instagram', 'insta', 'ig')),
    'Facebook': ('facebook', ('facebook', 'fb')), 'Messenger': ('messenger', ('messenger',)),
    'YouTube': ('youtube', ('youtube', 'yt')), 'WhatsApp': ('whatsapp', ('whatsapp',)), 'Snapchat': ('snapchat', ('snapchat',)),
    'Discord': ('discord', ('discord',)), 'Telegram': ('telegram', ('telegram',)), 'Threads': ('threads', ('threads',)),
    'X': ('x', ('twitter', 'x / twitter', 'x (twitter)')), 'Reddit': ('reddit', ('reddit',)), 'Roblox': ('roblox', ('roblox',)),
    'Minecraft': (None, ('minecraft',)), 'Fortnite': (None, ('fortnite',)), 'Steam': ('steam', ('steam',)),
    'Twitch': (None, ('twitch',)), 'Pinterest': ('pinterest', ('pinterest',)), 'LinkedIn': ('linkedin', ('linkedin',)),
    'Signal': ('signal', ('signal app',)), 'WeChat': ('wechat', ('wechat',)), 'Bluesky': ('bluesky', ('bluesky',)),
    'PlayStation': ('playstation', ('playstation', 'ps5')), 'Nintendo': ('nintendo', ('nintendo',)),
    'Epic Games': ('epicgames', ('epic games',)), 'Kick': ('kick', ('kick.com',)), 'Zoom': ('zoom', ('zoom app',)),
}
COUNTRY_ALIAS = {'usa': 'United States of America', 'us': 'United States of America', 'america': 'United States of America',
                 'united states': 'United States of America', 'uk': 'United Kingdom', 'britain': 'United Kingdom',
                 'great britain': 'United Kingdom', 'uae': 'United Arab Emirates', 'south korea': 'South Korea',
                 'korea': 'South Korea', 'czechia': 'Czechia'}
TONES = {'red': 'red', 'crimson': 'red', 'green': 'green', 'yellow': 'yellow', 'amber': 'yellow', 'orange': 'yellow',
         'gold': 'yellow', 'blue': 'blue'}
RED_WORDS = ('restrict', 'ban', 'block', 'lock', 'denied', 'illegal', 'warning', 'danger', 'risk', 'stop', 'no ')
GREEN_WORDS = ('unrestrict', 'allow', 'open', 'approved', 'safe', 'legal', 'free', 'yes')
DANGER = ('radical', 'exploit', 'abuse', 'harm', 'scam', 'danger', 'attack', 'death', 'loss', 'groom', 'extrem', 'risk')
CTA_VERBS = ('follow', 'subscribe', 'like', 'share', 'save', 'comment', 'visit', 'join', 'download', 'sign up', 'shop', 'tap')
GRAPHIC = re.compile(r'graphic|overlay|animat|chart|diagram|\bmap\b|\bstats?\b|statistic|callout|\bcard\b|icons?\b|logos?\b|'
                     r'banner|badge|stamp|counter|lower[ -]third|title card|\bui\b|mock-?up|closing frame|end (?:card|screen)|\bcta\b',
                     re.I)   # a line that names a graphic; anything else describes footage (a child tracing letters...)


def strip_emoji(t):
    return re.sub(r'\s{2,}', ' ', EMOJI.sub('', t)).strip()


def label_of(line):
    """'Split-Screen Graphic: ...' -> ('Split-Screen Graphic', '...'); no label -> ('', line)"""
    m = re.match(r'\s*[-•*]?\s*([A-Z][A-Za-z0-9 /&()\'.-]{1,48}?)\s*:\s*(.*)$', line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return '', line.strip()


CHILD = re.compile(r'^\s*(?:[-•*]|(?:left|right|top|bottom|side|panel|option|column|row|before|after|first|second)\b)', re.I)


def items(visuals):
    """VISUALS lines -> [{'label', 'text', 'children': [line, ...]}]. A labelled line with nothing after its colon opens a
    group ("Split-Screen Graphic:"); the lines under it that read as its parts (Left Side..., - ...) join it."""
    out, group = [], None
    for line in visuals:
        line = line.strip()
        if not line:
            continue
        lab, body = label_of(line)
        if group is not None and (CHILD.match(line) or not lab):
            group['children'].append(line)
            continue
        group = None
        it = {'label': lab, 'text': body, 'children': []}
        out.append(it)
        if lab and not body:
            group = it
    return out


def entities(text, folder_names=()):
    """platform / brand names in the order they appear (names a folder image carries count too)"""
    low, found = ' ' + text.lower() + ' ', []
    for name, (_, aliases) in PLATFORMS.items():
        for a in aliases:
            m = re.search(r'(?<![\w])' + re.escape(a) + r'(?![\w])', low)
            if m:
                found.append((m.start(), name)); break
    if re.search(r'(?<![\w])X(?![\w])', text) and not any(n == 'X' for _, n in found):
        found.append((text.index('X'), 'X'))
    for n in folder_names:
        if n and n not in {f for _, f in found} and re.search(r'(?<![\w])' + re.escape(n.lower()) + r'(?![\w])', low):
            found.append((low.index(n.lower()), n.title()))
    seen, out = set(), []
    for _, n in sorted(found):
        if n.lower() not in seen:
            seen.add(n.lower()); out.append(n)
    return out


def countries(text, names):
    """country names (from the map file) in order; aliases (USA, UK) map to the map's own names"""
    low, found = text.lower(), []
    for n in names:
        m = re.search(r'(?<![\w])' + re.escape(n.lower()) + r'(?![\w])', low)
        if m:
            found.append((m.start(), n))
    for a, n in COUNTRY_ALIAS.items():
        m = re.search(r'(?<![\w])' + re.escape(a) + r'(?![\w])', low)
        if m and n in names and n not in {x for _, x in found}:
            found.append((m.start(), n))
    return [n for _, n in sorted(found)]


def tone(text, default='red'):
    low = text.lower()
    for w, t in TONES.items():
        if re.search(r'\b' + w + r'\b', low):
            return t
    if any(w in low for w in GREEN_WORDS):
        return 'green'
    if any(w in low for w in RED_WORDS):
        return 'red'
    return default


def meaning(text, default):
    """a label's colour from what it says: allowed / safe -> green, banned / blocked -> red"""
    low = text.lower()
    return 'green' if any(w in low for w in GREEN_WORDS) else 'red' if any(w in low for w in RED_WORDS) else default


def banner(q):
    """'UNRESTRICTED: Gaming Platforms' -> ('UNRESTRICTED', 'GAMING PLATFORMS'); 'RESTRICTED' -> ('RESTRICTED', '')"""
    a, _, b = q.partition(':')
    return strip_emoji(a).strip().upper(), strip_emoji(b).strip().upper()


def kind_of(it):
    t = (it['label'] + ' ' + it['text'] + ' ' + ' '.join(it['children'])).lower()
    lab = it['label'].lower()
    if lab.startswith('transition') or re.match(r'(then|next)\b', t.strip()):
        return 'then'
    if re.search(r'closing frame|end (card|screen|frame)|outro card|\bcta\b', t) or any(t.strip().startswith(v) for v in CTA_VERBS):
        return 'cta'
    if not GRAPHIC.search(t) and len(re.findall(ARROWS, it['text'])) < 2:
        return 'shot'   # footage: "Split-screen of one child handwriting a letter and another typing" is two shots, not a graphic
    if 'split' in t or (it['children'] and any(re.match(r'\s*(left|right)\b', c, re.I) for c in it['children'])) or re.search(r'\bvs\.?\b', lab):
        return 'split'
    if re.search(r'flow ?chart|process|timeline|steps?\b', t) or len(re.findall(ARROWS, it['text'])) >= 2:
        return 'flow'
    if re.search(r'\bstat\b|statistic|callout|counter|figure|number', t) and re.search(r'\d', t):
        return 'stat'
    if re.search(r'\bmap\b', t):
        return 'map'
    if re.search(r'banner|stamp|badge|lock|overlay|icons?\b|logo', t) and not re.search(r'photo|footage|image of|picture of', t):
        return 'stamp'
    return 'custom'


def describe(it, kind, map_names=(), folder_names=()):
    """the data a graphic of this kind needs, read from its VISUALS text (the plan adds the times)"""
    whole = it['text'] + ' ' + ' '.join(it['children'])
    quotes = [strip_emoji(q).strip() for q in QUOTE.findall(whole)]
    g = {'kind': kind, 'label': it['label'], 'visual': (it['label'] + ': ' if it['label'] else '') + whole.strip()}
    if kind == 'stamp':
        low = whole.lower()
        g['device'] = 'phone' if re.search(r'phone|mobile|screen|device', low) else 'panel'
        g['apps'] = entities(whole, folder_names)
        txt, small = banner(quotes[0]) if quotes else ('', '')
        g['banner'] = {'text': txt, 'small': small, 'tone': tone(quotes[0] if quotes else low)}
        if re.search(r'lock', low):
            g['locks'] = True
    elif kind == 'split':
        sides = []
        parts = it['children'] or [p for p in re.split(r'\bvs\.?\b', it['text'], flags=re.I) if p.strip()]
        for c in parts[:2]:
            lab, body = label_of(c)
            m = re.search(r'\(([^)]+)\)', lab) or re.search(r'^\s*\(([^)]+)\)', body)
            name = (m.group(1) if m else lab or '').strip()
            q = [strip_emoji(x).strip() for x in QUOTE.findall(c)]
            low = c.lower()
            sides.append({'label': strip_emoji(name).upper(), 'items': entities(body or c, folder_names),
                          'label_tone': meaning(name, 'red' if not sides else 'green'),   # BANNED red, ALLOWED green
                          'badge': q[0].upper() if q else '', 'tone': tone(c, 'red' if not sides else 'yellow'),   # the badge
                          'blink': bool(re.search(r'blink|flash|pulse', low))})
        g['sides'] = sides
    elif kind == 'flow':
        body = it['text'] if re.search(ARROWS, it['text']) else ' '.join(it['children'])
        steps = [strip_emoji(s).strip(' .') for s in re.split(ARROWS, body) if strip_emoji(s).strip(' .')]
        g['title'] = ''
        g['steps'] = [{'text': s, 'danger': any(d in s.lower() for d in DANGER) and k == len(steps) - 1} for k, s in enumerate(steps)]
    elif kind == 'stat':
        num = next((q for q in quotes if re.search(r'\d', q)), quotes[0] if quotes else whole)
        m = re.search(r'((?:RM|[$€£])?\s?\d[\d,.]*\s?(?:%|k\b|m\b|million\b|billion\b|bn\b)?)\s*(.*)', num, re.I)
        g['value'], g['label_text'] = (m.group(1).strip(), m.group(2).strip()) if m else (num, '')
        note = next((q for q in quotes if q != num), '')
        src = re.search(r'\(([^)]*(?:study|survey|report|data|source|census|according)[^)]*)\)', note + ' ' + whole, re.I)
        g['source'] = src.group(1).strip() if src else ''
        g['note'] = re.sub(r'\s*\([^)]*\)', '', note).strip(' .') if note else ''
    elif kind == 'map':
        g['places'] = countries(whole, map_names)
        g['targets'] = [e for e in entities(whole, folder_names) if e not in g['places']]
    elif kind == 'cta':
        body = re.sub(r'^\s*(closing frame|end card|end screen|outro card)\s*[:\-–]\s*', '', it['text'], flags=re.I)
        body = re.sub(r'[\s\-–|]+\bCTA\b.*$', '', body, flags=re.I).strip()
        verb = next((v for v in CTA_VERBS if body.lower().startswith(v)), '')
        rest = body[len(verb):].strip()
        m = re.match(r'(.+?)\s+((?:for|to|on|and|&)\s.+)$', rest)
        name, tag = (m.group(1), m.group(2)) if m else (rest, '')
        g['cta'] = {'verb': verb.title(), 'name': name.strip(' .'), 'tagline': tag.strip(' .').lower(),
                    'handle': (re.search(r'@[\w.]+', whole) or [''])[0]}
    return g


def graphics(scene_visuals, map_names=(), folder_names=()):
    """one scene's VISUALS -> [graphic dicts]; a 'Transition' line becomes the previous graphic's 'then'"""
    out = []
    for it in items(scene_visuals):
        k = kind_of(it)
        if k == 'then' and out:
            whole = it['text'] + ' ' + ' '.join(it['children'])
            q = [strip_emoji(x).strip() for x in QUOTE.findall(whole)]
            txt, small = banner(q[0]) if q else ('', '')
            low = whole.lower()
            out[-1]['then'] = {'visual': (it['label'] + ': ' if it['label'] else '') + whole.strip(),
                               'banner': {'text': txt, 'small': small, 'tone': tone(q[0] if q else low, 'green')},
                               'icon': 'gamepad' if re.search(r'controller|gamepad|gaming|game', low) else '',
                               'say': small or txt}
            continue
        out.append(describe(it, 'custom' if k == 'then' else k, map_names, folder_names))
    return out


EMOJI_ICON = {'🚫': 'no', '⛔': 'no', '⚠': 'warn', '🎮': 'gamepad', '🎯': 'target', '📱': 'phone', '✅': 'check', '❌': 'cross',
              '❗': 'warn', '🔒': 'lock'}


def super_parts(text):
    """SUPER -> (clean text, icon name or ''): emojis become one leading icon (the fonts have no emoji), stray quotes go"""
    icon = next((EMOJI_ICON[c] for c in text if c in EMOJI_ICON), '')
    clean = strip_emoji(text).strip(' "“”\'')
    clean = re.sub(r'\s*[—–]\s*', ', ', clean)   # no em dashes on screen
    return re.sub(r'\s+([?!.,])', r'\1', clean), icon
