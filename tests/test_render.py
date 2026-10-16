#!/usr/bin/env python3
"""render.py speed planning tests: how many browsers, how long a session, where frames are, what the browser drew on.
Numbers from a 7 GB, 12-core laptop (90 frames of a 1080x1920 reel: 1 browser 95 s, 2 63 s, 3 47 s, ~0.6 GB each).
Standard library only:   python3 tests/test_render.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import render  # noqa: E402
import skillenv  # noqa: E402


class Browsers(unittest.TestCase):
    def test_every_browser_counts_against_free_ram(self):
        # the 7 GB laptop: 1.9 GB free -> 1 (as before), 2.5 GB -> 2, 3.5 GB -> 3
        self.assertEqual(render.plan_browsers(1900, 12), 1)
        self.assertEqual(render.plan_browsers(2500, 12), 2)
        self.assertEqual(render.plan_browsers(3500, 12), 3)

    def test_big_machine_is_capped(self):
        self.assertEqual(render.plan_browsers(55000, 16), 10)   # 64 GB, 16 cores
        self.assertEqual(render.plan_browsers(55000, 6), 5)     # cores - 1 leaves one for the system

    def test_unknown_or_tiny_means_one_browser_like_before(self):
        self.assertEqual(render.plan_browsers(None, 12), 1)
        self.assertEqual(render.plan_browsers(4000, None), 1)
        self.assertEqual(render.plan_browsers(800, 12), 1)
        self.assertEqual(render.plan_browsers(4000, 1), 1)


class Sessions(unittest.TestCase):
    def test_8_gb_and_less_keeps_150_frame_sessions(self):
        self.assertEqual(render.session_frames(7272, 2009), 150)
        self.assertEqual(render.session_frames(8192, 2009), 150)
        self.assertEqual(render.session_frames(None, 2009), 150)

    def test_bigger_machines_render_in_one_session(self):
        self.assertEqual(render.session_frames(65536, 2009), 2009)


class FrameFiles(unittest.TestCase):
    def test_one_browser_and_several_browsers_number_alike(self):
        one = 'renders/x_work/s00300/work-1/captured-frames/frame_000012.png'
        two = 'renders/x_work/s00300/work-1/capture-attempt-0/worker-1/frame_000053.png'
        self.assertEqual(render.frame_index(one, 300), 312)
        self.assertEqual(render.frame_index(two, 300), 353)


class DrawingDevice(unittest.TestCase):
    def test_reads_hyperframes_gpu_probe(self):
        line = ('[hyperframes] browserGpuMode probe → hardware (WebGL renderer vendor="Google Inc. (AMD)" '
                'renderer="ANGLE (AMD, AMD Radeon Graphics (radeonsi renoir ACO), OpenGL ES 3.2)")')
        self.assertEqual(render.drawing_on(line), 'hardware: AMD, AMD Radeon Graphics')
        self.assertEqual(render.drawing_on('[hyperframes] browserGpuMode probe → software'), 'software')
        self.assertEqual(render.drawing_on('no probe line'), 'unknown')


class Memory(unittest.TestCase):
    def test_linux_meminfo(self):
        text = 'MemTotal:        7446764 kB\nMemFree:          229832 kB\nMemAvailable:    3583420 kB\nCached:  1800000 kB\n'
        self.assertEqual(skillenv.parse_meminfo(text), (7272, 3499))

    def test_old_kernels_without_memavailable(self):
        self.assertEqual(skillenv.parse_meminfo('MemTotal: 2097152 kB\nMemFree: 524288 kB\nCached: 524288 kB\n'), (2048, 1024))

    def test_macos_vm_stat(self):
        text = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:                               100000.\n'
                'Pages active:                             500000.\nPages inactive:                           200000.\n'
                'Pages speculative:                         20000.\n')
        self.assertEqual(skillenv.parse_vm_stat(text, 17179869184), (16384, 5000))


class FastPng(unittest.TestCase):
    def test_preload_goes_into_node_options_as_a_file_url(self):
        env = render.fast_png_env({'NODE_OPTIONS': '--max-old-space-size=4096'})
        opt = env['NODE_OPTIONS']
        self.assertTrue(opt.startswith('--max-old-space-size=4096 --import file:'), opt)
        self.assertTrue(opt.endswith('hf_fastpng.mjs'))
        self.assertNotIn(' ', opt.split('--import ', 1)[1])   # a file URL: spaces in a user folder are %20
        self.assertTrue(os.path.isfile(os.path.join(ROOT, 'scripts', 'hf_fastpng.mjs')))

    def test_off_leaves_the_environment_alone(self):
        self.assertEqual(render.fast_png_env({'A': '1'}, on=False), {'A': '1'})

    def test_log_says_whether_it_engaged(self):
        self.assertTrue(render.fast_png_on('...\n[fastpng] fast lossless PNG capture on\n...'))
        self.assertFalse(render.fast_png_on('[fastpng] not applied (x): normal PNG capture'))


class Encode(unittest.TestCase):
    def test_live_encode_uses_the_same_settings(self):
        live = render.encode_args('ffmpeg', 'a.wav', '12', 100, 'o.mp4')
        after = render.encode_args('ffmpeg', 'a.wav', '12', 100, 'o.mp4', 'frames')
        self.assertIn('image2pipe', live)
        self.assertEqual(live[live.index('a.wav') - 1:], after[after.index('a.wav') - 1:])   # everything after the frames
        self.assertEqual(after[after.index('-crf') + 1], '12')
        self.assertTrue(after[after.index('-i') + 1].endswith('%05d.png'))

    def test_encoder_runs_behind_the_browsers(self):
        kw = render.low_priority()
        self.assertTrue(('creationflags' in kw) if os.name == 'nt' else ('preexec_fn' in kw))


class Assemble(unittest.TestCase):
    def test_shots_side_by_side(self):
        import assemble
        self.assertEqual(assemble.shots_at_once(20, 12), 3)
        self.assertEqual(assemble.shots_at_once(20, 2), 1)
        self.assertEqual(assemble.shots_at_once(2, 64), 2)
        self.assertEqual(assemble.shots_at_once(20, None), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
