#!/usr/bin/env python3
"""British English on screen: Whisper's American spelling converted, names and vocabulary left alone, and matching
that a British line cannot fail ("recognising" read as not heard against Whisper's "recognizing").
Standard library only:   python3 tests/test_spelling.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import check_edl  # noqa: E402
import spelling  # noqa: E402


class Words(unittest.TestCase):
    def check(self, pairs):
        for us, gb in pairs:
            self.assertEqual(spelling.british(us), gb, us)

    def test_ise_not_ize(self):
        self.check([('recognizing', 'recognising'), ('recognize', 'recognise'), ('realized', 'realised'),
                    ('organization', 'organisation'), ('emphasize', 'emphasise'), ('apologizes', 'apologises'),
                    ('organizer', 'organiser'), ('analyzing', 'analysing'), ('paralyzed', 'paralysed')])

    def test_words_that_keep_their_z(self):
        for w in ('size', 'sizes', 'resize', 'downsizing', 'prize', 'seized', 'capsized', 'maize', 'citizen', 'dozen',
                  'wizened', 'quizzes', 'Pfizer'):
            self.assertEqual(spelling.british(w), w)

    def test_our(self):
        self.check([('color', 'colour'), ('colors', 'colours'), ('colorful', 'colourful'), ('favorite', 'favourite'),
                    ('favoritism', 'favouritism'), ('behavioral', 'behavioural'), ('neighborhood', 'neighbourhood'),
                    ('honorable', 'honourable'), ('humor', 'humour'), ('colorization', 'colourisation')])
        for w in ('humorous', 'honorary', 'laboratory', 'vigorous', 'laborious', 'Colorado'):
            self.assertEqual(spelling.british(w), w)   # British has no u there either
        self.assertEqual(spelling.british('vaporize'), 'vaporise')

    def test_re_ll_and_the_rest(self):
        self.check([('center', 'centre'), ('centered', 'centred'), ('theater', 'theatre'), ('fiber', 'fibre'),
                    ('traveled', 'travelled'), ('traveling', 'travelling'), ('canceled', 'cancelled'),
                    ('modeling', 'modelling'), ('fueled', 'fuelled'), ('counselor', 'counsellor'),
                    ('gray', 'grey'), ('aging', 'ageing'), ('judgment', 'judgement'), ('jewelry', 'jewellery'),
                    ('defense', 'defence'), ('catalog', 'catalogue'), ('skeptical', 'sceptical'), ('mold', 'mould'),
                    ('pajamas', 'pyjamas'), ('fulfill', 'fulfil'), ('practicing', 'practising'), ('maneuver', 'manoeuvre')])

    def test_vocabulary_and_ambiguous_words_stay(self):
        for w in ('math', 'mom', 'apartment', 'license', 'practice', 'practices', 'program', 'meter', 'check', 'tire',
                  'draft', 'curb', 'story', 'learned'):
            self.assertEqual(spelling.british(w), w)

    def test_case_and_punctuation_kept(self):
        self.check([('Recognizing,', 'Recognising,'), ('COLOR', 'COLOUR'), ("color's", "colour's"), ('"center."', '"centre."'),
                    ('well-organized', 'well-organised'), ('GPT-5', 'GPT-5'), ("don't", "don't")])

    def test_british_input_is_left_as_it_is(self):
        for w in ('recognising', 'colour', 'centre', 'travelled', 'organisation', 'favourite', 'analyse'):
            self.assertEqual(spelling.british(w), w)
            self.assertEqual(spelling.british(spelling.british(w)), w)


class Lines(unittest.TestCase):
    def test_names_mid_sentence_keep_their_spelling(self):
        self.assertEqual(spelling.british_text('I kept recognizing the colors at Center Parcs. Center of it all.'),
                         'I kept recognising the colours at Center Parcs. Centre of it all.')
        self.assertEqual(spelling.british_text('the Pfizer team realized'), 'the Pfizer team realised')

    def test_whitespace_kept(self):
        self.assertEqual(spelling.british_text('  so  I realized\nthe color '), '  so  I realised\nthe colour ')

    def test_word_lists_from_whisper(self):
        self.assertEqual(spelling.british_words(['So', 'I', 'was', 'recognizing', 'Center', 'Parcs.', 'Center', 'it.']),
                         ['So', 'I', 'was', 'recognising', 'Center', 'Parcs.', 'Centre', 'it.'])


class Matching(unittest.TestCase):
    def test_key_is_spelling_blind(self):
        self.assertEqual(spelling.key('recognising'), spelling.key('Recognizing,'))
        self.assertEqual(spelling.key('Colour'), spelling.key('color.'))
        self.assertEqual(spelling.key('travelled'), spelling.key('traveled'))
        self.assertNotEqual(spelling.key('size'), spelling.key('sise'))

    def test_a_british_line_is_heard(self):
        """the Windows edit: the line said "recognising", Whisper heard "recognizing" -> the edge word was NOT HEARD"""
        line = 'I kept recognising the colours'.split()
        heard = 'I kept recognizing the colors'.split()
        self.assertEqual(check_edl.match([check_edl.norm(w) for w in line], [check_edl.norm(h) for h in heard]), [0, 1, 2, 3, 4])
        lm, le, tm, te = check_edl.edges(line, heard)
        self.assertEqual((lm, tm), ([], []))


if __name__ == '__main__':
    unittest.main(verbosity=2)
