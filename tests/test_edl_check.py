#!/usr/bin/env python3
"""EDL check tests (scripts/check_edl.py): a cut must never clip words its caption line says.
Built from the first cool girl reel, which opened on "actually really curious" because the in-point (2.08s) went
after a fast "So I was" (1.46-1.76s). Standard library only:   python3 tests/test_edl_check.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import check_edl  # noqa: E402
import skillenv  # noqa: E402

LINE = 'I was actually really curious about handwriting,'.split()
# what Whisper heard inside the shot [2.08, 3.56], and across the 1.5s before it (source times, as small.en gave them)
INSIDE = ['actually', 'really', 'curious', 'about', 'handwriting.']
AROUND = [('So', 1.30, 1.62), ('I', 1.66, 1.80), ('was', 1.86, 1.90), ('actually', 2.14, 2.36), ('really', 2.36, 2.58),
          ('curious', 2.58, 2.96), ('about', 2.96, 3.20), ('handwriting.', 3.20, 3.56)]


class FirstReelIncident(unittest.TestCase):
    def test_words_missing_at_the_start_are_found(self):
        lead_missing, lead_extra, trail_missing, trail_extra = check_edl.edges(LINE, INSIDE)
        self.assertEqual(lead_missing, ['I', 'was'])
        self.assertEqual(lead_extra, [])
        self.assertEqual(trail_missing, [])

    def test_nothing_heard_in_their_place_means_missing_not_misheard(self):
        self.assertEqual(check_edl.side_status(['I', 'was'], []), 'missing')

    def test_the_missing_words_are_said_just_before_the_in_point(self):
        hit = check_edl.clipped(['I', 'was'], AROUND, 'lead', 2.08)
        self.assertEqual([w for w, _, _ in hit], ['I', 'was'])
        self.assertLess(hit[-1][2], 2.08)

    def test_suggested_start_is_the_speech_onset_of_their_stretch(self):
        # 20ms envelope of 1.30-2.70s: "So I was" 1.46-1.76, pause, "actually..." from 2.14
        db = [-60] * 8 + [-30] * 15 + [-62] * 19 + [-25] * 28
        isl = check_edl.islands(db, thr=-45, t0=1.30)
        self.assertEqual(isl[0], (1.46, 1.76))
        self.assertEqual(check_edl.island_at(isl, 1.66, 'lead'), (1.46, 1.76))

    def test_the_fixed_edl_passes(self):
        line = 'So I was actually really curious about handwriting,'.split()
        heard = ['So', 'I', 'was', 'actually', 'really', 'curious', 'about', 'handwriting.']
        lm, le, tm, te = check_edl.edges(line, heard)
        self.assertEqual((lm, tm), ([], []))


class NotEveryMissWasACut(unittest.TestCase):
    def test_a_different_word_heard_in_its_place_is_a_mishearing(self):
        # s14 of the same reel: "were better at..." heard as "Or better at..."
        lm, le, tm, te = check_edl.edges('were better at recognizing'.split(), ['Or', 'better', 'at', 'recognizing'])
        self.assertEqual((lm, le), (['were'], ['Or']))
        self.assertEqual(check_edl.side_status(lm, le), 'misheard')

    def test_a_word_dropped_mid_line_is_not_an_edge_problem(self):
        lm, le, tm, te = check_edl.edges('and I came across this study'.split(), ['and', 'came', 'across', 'this', 'study'])
        self.assertEqual((lm, tm), ([], []))

    def test_hyphenated_words_split_by_whisper_still_match(self):
        lm, le, tm, te = check_edl.edges("isn't really old-fashioned.".split(), ["isn't", 'really', 'old', '-fashioned.'])
        self.assertEqual((lm, tm), ([], []))

    def test_heard_ok_accepts_words_someone_listened_to(self):
        self.assertEqual(check_edl.side_status(['I', 'was'], [], heard_ok=['I', 'was']), 'ok')

    def test_a_repeated_word_earlier_on_does_not_count_as_clipped(self):
        # "...grandmother. And I ... [cut] remember": the nearest "I" before the cut is the one that counts
        around = [('And', 7.0, 7.2), ('I', 7.2, 7.3), ('loved', 7.3, 7.6), ('it.', 7.6, 7.8), ('remember', 8.4, 8.9)]
        hit = check_edl.clipped(['I'], around, 'lead', 8.35)
        self.assertEqual(hit, [])   # "I" is not directly before the cut ("loved it." is): not this line's word


class TrailingWords(unittest.TestCase):
    def test_words_cut_off_at_the_end(self):
        line = 'because I was holding a pen or pencil too much.'.split()
        lm, le, tm, te = check_edl.edges(line, ['because', 'I', 'was', 'holding', 'a', 'pen', 'or', 'pencil', 'too'])
        self.assertEqual(tm, ['much.'])
        hit = check_edl.clipped(tm, [('too', 27.98, 28.32), ('much.', 28.32, 28.78)], 'trail', 28.40)
        self.assertEqual([w for w, _, _ in hit], ['much.'])


class CutPoints(unittest.TestCase):
    def test_a_cut_inside_continuous_sound_is_noticed(self):
        # "tiny callus on my fingers, so holding up": an out-point at 25.01 would cut the sound mid-stretch
        isl = [(23.76, 26.09)]
        self.assertEqual(check_edl.inside_sound(isl, 25.01, 'out'), (23.76, 26.09))
        self.assertIsNone(check_edl.inside_sound(isl, 26.30, 'out'))

    def test_a_word_dying_away_is_not_a_clipped_word(self):
        # first real run: out 19.88 with the sound fading out until 19.92 was flagged (12 of 20 shots looked like that)
        self.assertIsNone(check_edl.inside_sound([(19.08, 19.92)], 19.88, 'out'))
        # an in-point cutting "You know," off "maybe" (77.74 inside 77.38-78.18) is worth a note
        self.assertEqual(check_edl.inside_sound([(77.38, 78.18)], 77.74, 'in'), (77.38, 78.18))

    def test_dropped_stretches_between_shots(self):
        edl = [{'id': 's01', 'clip': 'c1', 'in': 2.08, 'out': 3.56}, {'id': 's02', 'clip': 'c1', 'in': 3.97, 'out': 7.67},
               {'id': 's03', 'clip': 'c1', 'in': 8.27, 'out': 12.08}]
        got = check_edl.gaps(edl, {'c1': 87.4})
        self.assertEqual(got[0], ('c1', 0.0, 2.08, None, 's01'))   # the head: where "So I was" was lost
        self.assertEqual(got[1], ('c1', 3.56, 3.97, 's01', 's02'))
        self.assertEqual(got[2], ('c1', 7.67, 8.27, 's02', 's03'))
        self.assertEqual(len(got), 3)   # the 75s tail is unused footage, not a trim

    def test_shots_out_of_source_order(self):
        edl = [{'id': 'b', 'clip': 'c1', 'in': 10.0, 'out': 12.0}, {'id': 'a', 'clip': 'c1', 'in': 1.0, 'out': 9.5}]
        self.assertEqual(check_edl.gaps(edl, {}), [('c1', 0.0, 1.0, None, 'a'), ('c1', 9.5, 10.0, 'a', 'b')])


class WhisperNoise(unittest.TestCase):
    def test_split_hyphen_words_are_glued_and_bare_dashes_dropped(self):
        self.assertEqual(check_edl.clean(['isn\'t', 'really', 'old', '-fashioned.']), ["isn't", 'really', 'old-fashioned.'])
        self.assertEqual(check_edl.clean([('fingers,', 24.9, 25.0), ('-', 25.0, 25.1)]), [('fingers,', 24.9, 25.0)])
        self.assertEqual(check_edl.clean([('old', 75.9, 76.1), ('-fashioned.', 76.1, 76.4)]), [('old-fashioned.', 75.9, 76.4)])

    def test_no_extra_word_after_a_hyphenated_last_word(self):
        lm, le, tm, te = check_edl.edges("isn't really old-fashioned.".split(), ["isn't", 'really', 'old', '-fashioned.'])
        self.assertEqual((tm, te), ([], []))

    def test_the_dropped_report_keeps_the_words_said_in_the_gap(self):
        # head of the clip, cut before s01: "So I was" (1.46-1.76), then "actually" belongs to the shot
        heard = [('So', 1.30, 1.62), ('I', 1.66, 1.80), ('was', 1.86, 1.90), ('actually', 2.14, 2.36)]
        isl = [(1.46, 1.76), (2.14, 3.92)]
        self.assertEqual([h[0] for h in check_edl.drop_words(heard, 0.0, 2.08, isl)], ['So', 'I', 'was'])

    def test_whisper_filling_silence_is_not_reported(self):
        # gap 32.85-33.86 is a pause; Whisper "heard" Thanks for watching! across it
        heard = [('effort', 32.24, 32.62), ('Thanks', 32.90, 33.30), ('for', 33.30, 33.45), ('watching!', 33.45, 33.80),
                 ('actually', 33.92, 34.40)]
        isl = [(30.38, 32.85), (33.92, 35.22)]
        self.assertEqual(check_edl.drop_words(heard, 32.85, 33.86, isl), [])

    def test_the_next_shots_first_word_does_not_leak_into_the_gap(self):
        # gap 19.88-20.35 is a pause; "writing" starts the next shot (sound from 20.41) but Whisper stamps it 19.98-20.66
        heard = [('of', 19.67, 19.87), ('writing', 19.98, 20.66), ('with', 20.66, 20.94)]
        isl = [(19.08, 19.92), (20.41, 23.15)]
        self.assertEqual(check_edl.drop_words(heard, 19.88, 20.35, isl), [])


class DroppedReport(unittest.TestCase):
    def test_kept_edge_words_spilling_into_the_gap_are_not_reported(self):
        got = check_edl.trim_kept(['fingers', 'so', 'holding', 'up'], 'tiny callus on my fingers,'.split(),
                                  'because I was holding a pen or pencil too much.'.split())
        self.assertEqual(got, ['so', 'holding', 'up'])
        self.assertEqual(check_edl.trim_kept(['actually'], 'And apparently all that effort'.split(), 'actually mattered.'.split()), [])

    def test_words_really_dropped_stay(self):
        # the editor wrote the line to match the clipped audio: "So I was" must show in the report
        got = check_edl.trim_kept(['So', 'I', 'was'], [], 'actually really curious about handwriting,'.split())
        self.assertEqual(got, ['So', 'I', 'was'])
        self.assertEqual(check_edl.trim_kept(['you', 'know.'], 'isnt really old-fashioned.'.split(), 'Maybe it is'.split()), ['you', 'know.'])


class WhisperDevice(unittest.TestCase):
    def test_gpu_only_when_its_libraries_load(self):
        # a GTX 1650 with the driver but no CUDA 12 runtime: faster-whisper picked cuda and died ("libcublas.so.12")
        self.assertEqual(skillenv.pick_device(1, False), 'cpu')
        self.assertEqual(skillenv.pick_device(0, True), 'cpu')
        self.assertEqual(skillenv.pick_device(1, True), 'cuda')


if __name__ == '__main__':
    unittest.main(verbosity=2)
