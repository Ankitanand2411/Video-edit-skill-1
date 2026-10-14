#!/usr/bin/env python3
"""Storyboard-mode logic tests. Standard library only:   python3 tests/test_storyboard.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
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


if __name__ == '__main__':
    unittest.main()
