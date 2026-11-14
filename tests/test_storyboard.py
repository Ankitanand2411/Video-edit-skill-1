#!/usr/bin/env python3
"""Storyboard-mode logic tests. Standard library only:   python3 tests/test_storyboard.py"""
import ast
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import check_edl  # noqa: E402
import sbgraphics  # noqa: E402
import skillenv  # noqa: E402
import storyboard  # noqa: E402
import storyboard_plan  # noqa: E402

CELL = """VISUALS:

Close-up of a child's fingers gripping a pencil.
Pencil tip pressing against paper.

SUPER:
All those little efforts add up.

SCRIPT / VO:

I even had this tiny callus on my finger.

And apparently, all that effort mattered."""


class Blocks(unittest.TestCase):
    def test_three_blocks(self):
        b = storyboard.blocks(CELL)
        self.assertEqual(b['visuals'], ["Close-up of a child's fingers gripping a pencil.", 'Pencil tip pressing against paper.'])
        self.assertEqual(b['super'], 'All those little efforts add up.')
        self.assertEqual(b['script'], 'I even had this tiny callus on my finger. And apparently, all that effort mattered.')

    def test_missing_super(self):
        b = storyboard.blocks('VISUALS:\nA child reading.\nSCRIPT / VO:\nRead it.')
        self.assertEqual(b['super'], '')
        self.assertEqual(b['script'], 'Read it.')

    def test_column_letters(self):
        self.assertEqual(storyboard.col_index('A1'), 0)
        self.assertEqual(storyboard.col_index('F7'), 5)
        self.assertEqual(storyboard.col_index('AB12'), 27)


class Matching(unittest.TestCase):
    def test_stems_meet(self):
        s = storyboard_plan.stem
        self.assertEqual(s('write'), s('writing'))
        self.assertEqual(s('writing'), s('written'))
        self.assertEqual(s('kids'), s('child'))
        self.assertEqual(s('letters'), s('letter'))
        self.assertEqual(s('Handwriting,'), s('write'))

    def test_keywords_skip_stop_words(self):
        k = storyboard_plan.keywords('Close-up of a young child sitting beside their grandmother at a table')
        self.assertIn(storyboard_plan.stem('grandmother'), k)
        self.assertNotIn('of', k)
        self.assertNotIn('their', k)


class HyperframesEnv(unittest.TestCase):
    def test_cuda_download_skipped(self):
        env = skillenv.hyperframes_env(environ={'PATH': '/usr/bin'})
        self.assertEqual(env['ONNXRUNTIME_NODE_INSTALL_CUDA'], 'skip')
        env = skillenv.hyperframes_env(environ={'PATH': '/usr/bin', 'ONNXRUNTIME_NODE_INSTALL_CUDA': 'v12'})
        self.assertEqual(env['ONNXRUNTIME_NODE_INSTALL_CUDA'], 'v12')   # the user's own choice wins


# the under-16 news storyboard: no pictures in the sheet, every VISUALS line a graphic (the first cut skipped them all)
U16 = {
    'HOOK': ['Animated Overlay: A smartphone graphic showing locked social media icons (TikTok, IG, Facebook) with a prominent '
             'red "RESTRICTED" banner across them.',
             'Transition Graphic: The banner flips over to reveal a glowing green gaming controller icon with an arrow pointing '
             'to "UNRESTRICTED: Gaming Platforms".'],
    'SCENE 2': ['Split-Screen Graphic:', 'Left Side (Banned): TikTok, Instagram, Facebook icons with red "Under 16 Ban" badge.',
                'Right Side (Allowed): Roblox, Minecraft logos with a blinking yellow "NO REGULATION" warning indicator.'],
    'SCENE 3': ['Flowchart Infographic:In-Game Chat (Roblox) ➔ Befriending & Building Trust ➔ Private Groups (Discord) ➔ '
                'Radicalization / Exploitation',
                'Stat Callout Card: "100,000 Malaysian Kids" (Highlighted in bold text overlay) | "Exposed to online sexual '
                'exploitation/abuse (UNICEF Study)".'],
    'SCENE 4': ['Interactive Map Graphic: Highlights Australia 🇦🇺 and Malaysia 🇲🇾 with animated connectivity lines pointing to '
                'platform logos (Roblox / Minecraft).'],
    'Outro': ['Closing Frame: Follow School Advisor for more education News - CTA'],
}
MAP = ['Australia', 'Malaysia', 'Indonesia', 'United States of America']


class Graphics(unittest.TestCase):
    def test_every_line_is_a_graphic(self):
        kinds = {k: [g['kind'] for g in sbgraphics.graphics(v, MAP)] for k, v in U16.items()}
        self.assertEqual(kinds, {'HOOK': ['stamp'], 'SCENE 2': ['split'], 'SCENE 3': ['flow', 'stat'], 'SCENE 4': ['map'],
                                 'Outro': ['cta']})

    def test_stamp_and_its_flip(self):
        g = sbgraphics.graphics(U16['HOOK'], MAP)[0]
        self.assertEqual(g['apps'], ['TikTok', 'Instagram', 'Facebook'])   # "IG" is Instagram
        self.assertEqual((g['banner']['text'], g['banner']['tone']), ('RESTRICTED', 'red'))
        self.assertTrue(g['locks'])
        self.assertEqual((g['then']['banner']['text'], g['then']['banner']['small'], g['then']['banner']['tone'], g['then']['icon']),
                         ('UNRESTRICTED', 'Gaming Platforms', 'green', 'gamepad'))   # as the storyboard writes it

    def test_split_sides(self):
        a, b = sbgraphics.graphics(U16['SCENE 2'], MAP)[0]['sides']
        self.assertEqual((a['label'], a['items'], a['badge'], a['tone'], a['blink']),
                         ('Banned', ['TikTok', 'Instagram', 'Facebook'], 'Under 16 Ban', 'red', False))   # as written
        self.assertEqual((b['label'], b['items'], b['badge'], b['tone'], b['blink']),
                         ('Allowed', ['Roblox', 'Minecraft'], 'NO REGULATION', 'yellow', True))
        self.assertEqual((a['label_tone'], b['label_tone']), ('red', 'green'))   # the chips say what the side means

    def test_flow_and_stat(self):
        flow, stat = sbgraphics.graphics(U16['SCENE 3'], MAP)
        self.assertEqual([s['text'] for s in flow['steps']], ['In-Game Chat (Roblox)', 'Befriending & Building Trust',
                                                              'Private Groups (Discord)', 'Radicalization / Exploitation'])
        self.assertEqual([s['danger'] for s in flow['steps']], [False, False, False, True])   # the harm, in red
        self.assertEqual((stat['value'], stat['label_text'], stat['source'], stat['note']),
                         ('100,000', 'Malaysian Kids', 'UNICEF Study', 'Exposed to online sexual exploitation/abuse'))

    def test_map_and_cta(self):
        m = sbgraphics.graphics(U16['SCENE 4'], MAP)[0]
        self.assertEqual((m['places'], m['targets']), (['Australia', 'Malaysia'], ['Roblox', 'Minecraft']))
        c = sbgraphics.graphics(U16['Outro'], MAP)[0]['cta']
        self.assertEqual((c['verb'], c['name'], c['tagline']), ('Follow', 'School Advisor', 'for more education News'))   # as written

    def test_footage_is_not_a_graphic(self):   # the handwriting storyboard: its pictures carry these lines
        for line in ("Close-up of a child's fingers gripping a pencil.", 'Child identifying a letter on a worksheet.',
                     'Split-screen of one child handwriting a letter and another typing the same letter on a keyboard.',
                     "Grandmother gently guiding the child's hand across a piece of paper."):
            self.assertEqual(sbgraphics.graphics([line], MAP)[0]['kind'], 'shot', line)

    def test_super_emoji_becomes_an_icon(self):
        self.assertEqual(sbgraphics.super_parts('No Social Media Under 16? 🚫📱"'), ('No Social Media Under 16?', 'no'))
        self.assertEqual(sbgraphics.super_parts('"⚠️ POLICE WARNING: In-Game Recruitment"'), ('POLICE WARNING: In-Game Recruitment', 'warn'))
        self.assertEqual(sbgraphics.super_parts('Are We Protecting Kids—Or Missing The Target? 🎯❓')[0],
                         'Are We Protecting Kids, Or Missing The Target?')   # no em dash on screen


def words_of(text, t0=0.0, step=.4):
    return [{'text': w, 'start': round(t0 + k * step, 3), 'end': round(t0 + k * step + .3, 3)} for k, w in enumerate(text.split())]


class PlanTiming(unittest.TestCase):
    W = words_of('They do it by befriending a child in-game, building trust, then moving the conversation into private chat '
                 'groups such as Discord where the kids get exposed to extremist ideologies. A UNICEF study in 2022 estimated '
                 'that 100,000 Malaysian children experienced online sexual exploitation or abuse within a single year.')

    def idx(self, word):
        return next(i for i, w in enumerate(self.W) if w['text'].strip('.,') == word)

    def test_step_lights_on_its_first_keyword_said(self):
        after = self.idx('private')
        i = storyboard_plan.find(self.W, 'Radicalization / Exploitation', 0, 99, after)
        self.assertEqual(self.W[i]['text'], 'extremist')   # not "exploitation" in the next sentence

    def test_phrase_with_words_between(self):
        self.assertEqual(storyboard_plan.find(self.W, 'Private Groups (Discord)', 0, 99), self.idx('private'))

    def test_number_by_its_digits(self):
        self.assertEqual(storyboard_plan.find(self.W, '100,000', 0, 99, single=False), self.idx('100,000'))
        split = words_of('estimated that 100 ,000 Malaysian children')   # Whisper's split
        self.assertEqual(split[storyboard_plan.find(split, '100,000', 0, 99, single=False)]['text'], '100')

    def test_sentence_end(self):
        self.assertEqual(storyboard_plan.sentence_end(self.W, self.idx('Discord')), self.W[self.idx('ideologies')]['end'])

    def test_british_and_american_meet(self):
        self.assertEqual(storyboard_plan.stem('radicalisation'), storyboard_plan.stem('Radicalization'))


class FolderPictures(unittest.TestCase):
    def test_names_from_file_names(self):
        d = tempfile.mkdtemp()
        try:
            for fn in ('roblox logo.jpg', 'minecraft image.jpg', 'images logo.png', 'notes.txt', 'board.xlsx'):
                open(os.path.join(d, fn), 'wb').close()
            proj = os.path.join(d, 'proj')
            got = {f['source']: (f['names'], f['kind']) for f in storyboard.folder_images(os.path.join(d, 'board.xlsx'), proj)}
            self.assertEqual(got, {'images logo.png': ([], 'logo'), 'minecraft image.jpg': (['minecraft'], 'photo'),
                                   'roblox logo.jpg': (['roblox'], 'logo')})   # no name: LOOK at it and name it
            self.assertTrue(os.path.isfile(os.path.join(proj, 'assets', 'storyboard', 'folder', 'roblox-logo.jpg')))
        finally:
            shutil.rmtree(d)


class OpeningSilence(unittest.TestCase):
    def test_gap_before_first_word(self):
        self.assertEqual(check_edl.opening_gap([('Malaysia', 2.28, 2.9)], 1.07), 1.21)   # v1 of the under-16 reel
        self.assertGreater(check_edl.opening_gap([('Malaysia', 2.28, 2.9)], 1.07), check_edl.OPEN_GAP)
        self.assertLess(check_edl.opening_gap([('Malaysia', 1.14, 1.9)], 1.07), check_edl.OPEN_GAP)
        self.assertEqual(check_edl.opening_gap([], 1.0), 0.0)


def template(names, ns):
    """some functions of assets/template/build.py, without running the build (it reads a project)"""
    src = open(os.path.join(ROOT, 'assets', 'template', 'build.py'), encoding='utf-8').read()
    keep = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=keep, type_ignores=[]), 'build.py', 'exec'), ns)
    return ns


class ScreenCase(unittest.TestCase):
    T = template({'shown', 'bare', 'script_tokens', 'storyboard_forms'},
                 {'re': re, 'PROPER': {'malaysia', 'tiktok', 'roblox', 'australia'}, 'SPELL': None,
                  'norm': lambda t: re.sub(r"[^\w'-]", '', t).lower().replace('isation', 'ization')})

    def test_names_keep_capitals_without_a_storyboard(self):
        shown = self.T['shown']
        self.assertEqual([shown(w) for w in ('Sounds', 'TikTok,', 'MCMC', "Malaysia's", 'UNICEF', 'So', 'I', 'Australia')],
                         ['sounds', 'TikTok,', 'MCMC', "Malaysia's", 'UNICEF', 'so', 'I', 'Australia'])

    def test_digit_grouping_kept(self):   # the first news reel captioned "100000"
        bare = self.T['bare']
        self.assertEqual([bare(w) for w in ('100,000', 'TikTok,', '16.', '1.5', "Malaysia's", 'in-game,')],
                         ['100,000', 'TikTok', '16', '1.5', "Malaysia's", 'in-game'])

    def test_captions_take_the_scripts_words(self):
        ns = template({'bare', 'script_tokens', 'storyboard_forms'},
                      {'re': re, 'SPELL': None, 'norm': lambda t: re.sub(r"[^\w'-]", '', t).lower().replace('isation', 'ization')})
        ns['SWAPS'] = []
        ns['SB_DOC'] = {'scenes': [{'script': "Malaysia's former Deputy Police Chief warned that children as young as 12 had been "
                                              'recruited... from grooming and radicalization. Here at home, MCMC is now looking.'}]}
        said = "Malaysia's former deputy police chief warned that kids as young as 12 radicalisation. here at home, MCMC".split()
        ns['WORDS'] = [{'text': w, 'shown': w} for w in said]
        ns['storyboard_forms']()
        got = [w['shown'] for w in ns['WORDS']]
        self.assertEqual(got[:5], ["Malaysia's", 'former', 'Deputy', 'Police', 'Chief'])   # the script's capitals
        self.assertEqual(got[7], 'children')   # a one-word slip inside a scripted sentence: the script's word (its grammar)
        self.assertIn('radicalization.', got)                                              # the script's spelling + its full stop
        self.assertEqual(got[-4:], ['Here', 'at', 'home,', 'MCMC'])
        self.assertEqual(got[:2], ["Malaysia's", 'former'])
        self.assertEqual(len(ns['SWAPS']), 1)   # kids -> children, printed for review


class BrandAndMotion(unittest.TestCase):
    def test_brand_from_the_storyboard(self):
        self.assertEqual(storyboard.brand_of(['SA _News_3Nov2026_Video 2-Is Malaysia_s Under-16 ...xlsx']), 'schooladvisor')
        self.assertEqual(storyboard.brand_of(['Closing Frame: Follow School Advisor for more education News - CTA']), 'schooladvisor')
        self.assertEqual(storyboard.brand_of(['BRAND', 'Afterschool', 'Exam tips for SPM']), 'afterschool')
        self.assertIsNone(storyboard.brand_of(['How handwriting helps the brain learn to read']))

    def test_picture_animation_from_visuals(self):
        a = storyboard_plan.card_anim
        self.assertEqual(a('Campus photo slides in from the left as he names it'), 'slide-left')
        self.assertEqual(a('Slow zoom in on the boarding house'), 'push')
        self.assertEqual(a('Ken Burns on the aerial shot of the 90-acre campus'), 'push')
        self.assertEqual(a('Zoom out to reveal the whole school'), 'pull')
        self.assertEqual(a('Logo pops up beside him'), 'pop')
        self.assertEqual(a('Students in the library'), '')

if __name__ == '__main__':
    unittest.main()
