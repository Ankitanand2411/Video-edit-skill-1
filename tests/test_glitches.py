#!/usr/bin/env python3
"""The revisions of a delivered reel (spm grade boundaries): words behind the head losing letters for 4-17 frames,
a cutout silhouette sitting ~90px above the head, shots opening on the host leaning back from the phone.
Standard library only:   python3 tests/test_glitches.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import cutout  # noqa: E402
import headpos  # noqa: E402
import wordcheck  # noqa: E402

# own-colour pixels of "cambridge" in the delivered reel, frame by frame: "cam   ge" for 17 frames, then whole
CAMBRIDGE = [11532, 11559, 11537, 9572, 10115, 10112, 11679, 11679, 11698, 11702, 11707, 11696, 11697, 11701, 11698, 11748,
             11768, 13432, 13688, 15188, 14923, 15277, 15612, 15813, 15871, 15928, 15974]


class WordGlitch(unittest.TestCase):
    def test_the_delivered_glitch(self):
        self.assertEqual(wordcheck.glitch_runs(CAMBRIDGE), [(0, 17)])

    def test_a_short_dropout(self):
        self.assertEqual(wordcheck.glitch_runs([15000] * 10 + [9000, 9100] + [15000] * 10), [(10, 11)])

    def test_head_moving_is_not_a_glitch(self):
        self.assertEqual(wordcheck.glitch_runs([20000 - 150 * i for i in range(30)]), [])   # the hair rising into the letters
        self.assertEqual(wordcheck.glitch_runs([15000 + (i % 3) * 50 for i in range(30)]), [])   # compression noise

    def test_colour(self):
        self.assertEqual(wordcheck.colour('#FAE67A'), (250, 230, 122))


class CutoutJump(unittest.TestCase):
    def test_silhouette_jump(self):
        self.assertEqual(cutout.first_jump([800] * 10 + [700] * 5 + [800] * 10, 100, set()), (110, 100))

    def test_real_movement_and_cuts(self):
        self.assertIsNone(cutout.first_jump([800, 796, 792, 788] * 5, 100, set()))   # 4px a frame: measured max on 12 pieces
        self.assertIsNone(cutout.first_jump([800] * 10 + [600] * 10, 100, {110}))     # a cut to a close-up


class Leaning(unittest.TestCase):
    def test_close_to_the_lens(self):
        # widths of [first frame, 20%, 50%, 80%, last frame]; the clip's usual head is 300px wide at zoom 1
        self.assertEqual(headpos.leaning([560, 310, 300, 305, 300], 1.0, 300), [0])
        self.assertEqual(headpos.leaning([300, 300, 300, 300, 520], 1.0, 300), [4])

    def test_a_close_up_is_not_a_lean(self):
        self.assertEqual(headpos.leaning([405, 400, 410, 400, 405], 1.35, 300), [])   # zoom 1.35 taken out


if __name__ == '__main__':
    unittest.main()
