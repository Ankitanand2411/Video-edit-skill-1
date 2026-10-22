#!/usr/bin/env python3
"""British spelling for every word the reel shows. Whisper (small.en, medium.en) spells the American way whatever the
accent ("recognizing", "color", "center", "traveled"); the skill writes British, with -ise: recognising, colour,
centre, travelled. Standard library only.

  british(word)          one word: case and the punctuation around it kept ("Recognizing," -> "Recognising,")
  british_text(text)     a line or a sentence, word by word, except a capitalised word in the middle of a sentence:
                         a name or brand keeps its own spelling ("Center Parcs", "the Pfizer vaccine")
  british_words(words)   the same over a list of single words (Whisper's word list), sentence by sentence
  key(word)              a spelling-blind matching key: the line's "recognising" and Whisper's "recognizing" are one
                         word (check_edl.py and align.py match with it; matching letter for letter failed these)

Only spelling variants of the same word change, never the vocabulary: captions say what was said ("math", "mom",
"apartment" stay). Words whose British spelling depends on the meaning stay as written: license / licence,
practice / practise (the -ing / -ed forms are always verbs, so those change), program / programme, meter / metre,
check / cheque, tire / tyre, draft / draught, curb / kerb, story / storey.
"""
import re

# whole words, American -> British (inflected forms listed: a rule would guess wrong on these)
WORDS = {
    'center': 'centre', 'centers': 'centres', 'centered': 'centred', 'centering': 'centring', 'centerpiece': 'centrepiece',
    'centerpieces': 'centrepieces', 'epicenter': 'epicentre', 'theater': 'theatre', 'theaters': 'theatres',
    'liter': 'litre', 'liters': 'litres', 'fiber': 'fibre', 'fibers': 'fibres', 'caliber': 'calibre', 'somber': 'sombre',
    'saber': 'sabre', 'specter': 'spectre', 'luster': 'lustre', 'meager': 'meagre', 'scepter': 'sceptre',
    'maneuver': 'manoeuvre', 'maneuvers': 'manoeuvres', 'maneuvered': 'manoeuvred', 'maneuvering': 'manoeuvring',
    'gray': 'grey', 'grays': 'greys', 'grayish': 'greyish', 'aging': 'ageing',
    'judgment': 'judgement', 'judgments': 'judgements', 'acknowledgment': 'acknowledgement',
    'acknowledgments': 'acknowledgements', 'jewelry': 'jewellery',
    'catalog': 'catalogue', 'catalogs': 'catalogues', 'cataloged': 'catalogued', 'cataloging': 'cataloguing',
    'dialog': 'dialogue', 'dialogs': 'dialogues', 'analog': 'analogue', 'monolog': 'monologue', 'prolog': 'prologue',
    'epilog': 'epilogue',
    'defense': 'defence', 'defenses': 'defences', 'offense': 'offence', 'offenses': 'offences', 'pretense': 'pretence',
    'skeptic': 'sceptic', 'skeptics': 'sceptics', 'skeptical': 'sceptical', 'skeptically': 'sceptically',
    'skepticism': 'scepticism',
    'mold': 'mould', 'molds': 'moulds', 'molded': 'moulded', 'molding': 'moulding', 'moldy': 'mouldy',
    'smolder': 'smoulder', 'smoldering': 'smouldering', 'molt': 'moult',
    'plow': 'plough', 'plows': 'ploughs', 'plowed': 'ploughed', 'plowing': 'ploughing',
    'cozy': 'cosy', 'cozier': 'cosier', 'coziest': 'cosiest', 'pajamas': 'pyjamas',
    'fulfill': 'fulfil', 'fulfills': 'fulfils', 'fulfillment': 'fulfilment', 'enroll': 'enrol', 'enrolls': 'enrols',
    'enrollment': 'enrolment', 'installment': 'instalment', 'installments': 'instalments', 'skillful': 'skilful',
    'skillfully': 'skilfully', 'willful': 'wilful', 'willfully': 'wilfully', 'distill': 'distil', 'instill': 'instil',
    'instills': 'instils',
    'artifact': 'artefact', 'artifacts': 'artefacts', 'esthetic': 'aesthetic', 'esthetics': 'aesthetics',
    'pediatric': 'paediatric', 'pediatrician': 'paediatrician', 'pediatricians': 'paediatricians', 'anemia': 'anaemia',
    'anemic': 'anaemic', 'anesthesia': 'anaesthesia', 'anesthetic': 'anaesthetic', 'estrogen': 'oestrogen',
    'fetus': 'foetus', 'leukemia': 'leukaemia', 'hemoglobin': 'haemoglobin', 'hemorrhage': 'haemorrhage',
    'orthopedic': 'orthopaedic', 'encyclopedia': 'encyclopaedia', 'archeology': 'archaeology',
    'archeologist': 'archaeologist',
    'mustache': 'moustache', 'mustaches': 'moustaches', 'donut': 'doughnut', 'donuts': 'doughnuts',
    'licorice': 'liquorice', 'sulfur': 'sulphur', 'ax': 'axe',
    'cancelation': 'cancellation', 'cancelations': 'cancellations', 'counselor': 'counsellor',
    'counselors': 'counsellors', 'marvelous': 'marvellous', 'marvelously': 'marvellously', 'panelist': 'panellist',
    'panelists': 'panellists', 'worshiped': 'worshipped', 'worshiping': 'worshipping', 'worshiper': 'worshipper',
    'woolen': 'woollen',
    'practicing': 'practising', 'practiced': 'practised',
}
# -or -> -our, with the endings that keep the u in British (honorary, humorous, laboratory, vigorous keep no u)
OUR = ('arbor', 'ardor', 'armor', 'behavior', 'candor', 'clamor', 'color', 'demeanor', 'endeavor', 'favor', 'fervor',
       'flavor', 'harbor', 'honor', 'humor', 'labor', 'neighbor', 'odor', 'parlor', 'rancor', 'rigor', 'rumor', 'savior',
       'savor', 'splendor', 'tumor', 'valor', 'vapor', 'vigor')
OUR_ENDINGS = ('', 's', 'ed', 'ing', 'ings', 'ful', 'fully', 'less', 'able', 'ably', 'ite', 'ites', 'er', 'ers', 'hood',
               'hoods', 'ist', 'ists', 'y', 'al', 'ally', 'ism', 'ly', 'liness', 'itism', 'ization', 'izations')
# a single l doubled before -ed / -ing / -er in British (traveled -> travelled)
DOUBLE_L = ('travel', 'cancel', 'label', 'model', 'fuel', 'level', 'signal', 'channel', 'counsel', 'jewel', 'marvel',
            'quarrel', 'tunnel', 'total', 'equal', 'duel', 'rival', 'funnel', 'shovel', 'snorkel', 'pencil', 'dial',
            'yodel', 'grovel', 'panel', 'tinsel', 'swivel', 'unravel', 'refuel', 'spiral', 'initial', 'gravel', 'barrel',
            'bevel', 'enamel', 'libel', 'pedal', 'shrivel', 'towel', 'trowel', 'snivel', 'stencil', 'tassel')
L_ENDINGS = ('ed', 'ing', 'ings', 'er', 'ers')
# -ize / -yze -> -ise / -yse, except where British keeps the z too
IZE = re.compile(r'^([a-z]{2,}?)(iz|yz)(e|es|ed|ing|ings|er|ers|ation|ations|ational|able)$')
KEEP_Z = {'size', 'resize', 'oversize', 'undersize', 'downsize', 'upsize', 'outsize', 'bitesize', 'supersize',
          'prize', 'seize', 'capsize', 'maize', 'baize', 'assize'}
KEEP = {'pfizer'}   # names that look like an -ize word


def _lower(w):
    """lowercase word -> British (or the word itself). The rules apply one after another: "colorization" gets its u
    and its s."""
    if w in KEEP:
        return w
    if w in WORDS:
        return WORDS[w]
    for stem in OUR:
        if w.startswith(stem) and w[len(stem):] in OUR_ENDINGS:
            w = stem[:-2] + 'our' + w[len(stem):]   # color -> col + our
            break
    for stem in DOUBLE_L:
        if w.startswith(stem) and w[len(stem):] in L_ENDINGS:
            w = stem + 'l' + w[len(stem):]
            break
    m = IZE.match(w)
    if m and m.group(1) + m.group(2) + 'e' not in KEEP_Z:
        w = m.group(1) + ('is' if m.group(2) == 'iz' else 'ys') + m.group(3)
    return w


def _cased(src, out):
    if src.isupper() and len(src) > 1:
        return out.upper()
    if src[:1].isupper():
        return out[:1].upper() + out[1:]
    return out


TOKEN = re.compile(r"^(\W*)([A-Za-z][A-Za-z'-]*?)((?:'[A-Za-z]+)?)(\W*)$")


def british(word):
    """one word, punctuation and case kept; hyphenated parts each ("well-organized" -> "well-organised")"""
    m = TOKEN.match(word)
    if not m:
        return word
    lead, core, poss, trail = m.groups()
    parts = core.split('-')
    return lead + '-'.join(_cased(p, _lower(p.lower())) if p else p for p in parts) + poss + trail


def british_words(words):
    """[word, ...] -> British, skipping a capitalised word in the middle of a sentence (a name or a brand)"""
    out, start = [], True
    for w in words:
        core = w.strip().lstrip('"\'(“‘')
        name = core[:1].isupper() and not start and core not in ('I',) and not core.startswith("I'")
        out.append(w if name else british(w))
        if w.strip():
            start = bool(re.search(r'[.!?…]["\'”’)]*\s*$', w))
    return out


def british_text(text):
    """a line -> British, whitespace kept exactly"""
    parts = re.split(r'(\s+)', text)
    words = british_words([p for p in parts if p and not p.isspace()])
    it = iter(words)
    return ''.join(p if (not p or p.isspace()) else next(it) for p in parts)


def key(word):
    """spelling-blind matching key: lowercase, letters / digits / apostrophes only, British spelling"""
    w = re.sub(r"[^\w']", '', word.lower().replace('-', ''))
    return _lower(w)
