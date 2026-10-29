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

    def test_small_machines_leave_room_for_the_app(self):
        # 8 GB laptop: 3 browsers ran the system out of memory at ~3.2 and ~4.2 GB free (the OOM killer took the app)
        self.assertEqual(render.plan_browsers(3230, 12, per=render.SMALL_PER_MB, reserve=render.SMALL_RESERVE_MB), 1)
        self.assertEqual(render.plan_browsers(4200, 12, per=render.SMALL_PER_MB, reserve=render.SMALL_RESERVE_MB), 2)
        self.assertEqual(render.plan_browsers(3230, 12), 3)   # the old budget

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


class WindowsRender(unittest.TestCase):
    """the first Windows render crashed: frames never seen (work folder in %TEMP%) and Node out of heap"""

    def test_node_heap_grows_with_the_browsers(self):
        self.assertEqual(render.node_heap_mb(1), 1024 + 768)
        self.assertEqual(render.node_heap_mb(10), 1024 + 7680)   # HyperFrames' own plan: 1024 + 640 a browser
        env = render.heap_env({'NODE_OPTIONS': '--import file:///x.mjs'}, 5)
        self.assertEqual(env['NODE_OPTIONS'], f'--import file:///x.mjs --max-old-space-size={render.node_heap_mb(5)}')
        self.assertEqual(render.heap_env({'NODE_OPTIONS': '--max-old-space-size=30000'}, 5)['NODE_OPTIONS'],
                         '--max-old-space-size=30000')          # a bigger heap the user set stays
        self.assertEqual(render.heap_env({'NODE_OPTIONS': '--max-old-space-size=512'}, 2)['NODE_OPTIONS'],
                         f'--max-old-space-size={render.node_heap_mb(2)}')

    def test_frames_are_found_in_the_temp_folder_and_retries(self):
        import tempfile
        with tempfile.TemporaryDirectory() as cdir:
            tmp_work = tempfile.mkdtemp(prefix='hf-render-')   # where HyperFrames works on Windows
            try:
                os.makedirs(os.path.join(cdir, 'work-abc-1', 'captured-frames'))
                self.assertIn(tmp_work, render.work_dirs(cdir))
                self.assertIn(os.path.join(cdir, 'work-abc-1'), render.work_dirs(cdir))
                for d in ('captured-frames', os.path.join('capture-attempt-1', 'worker-0'), 'retry-1-batch-0-worker-2'):
                    os.makedirs(os.path.join(tmp_work, d), exist_ok=True)
                    open(os.path.join(tmp_work, d, 'frame_000007.png'), 'w').close()
                self.assertEqual(len(render.live_frames(tmp_work)), 3)
            finally:
                import shutil
                shutil.rmtree(tmp_work, ignore_errors=True)


@unittest.skipUnless(skillenv.tool('ffmpeg'), 'needs ffmpeg')
class MusicMix(unittest.TestCase):
    def test_a_reel_with_a_music_bed_mixes(self):
        # ffmpeg 6.1 refused the music fade-in written 'd=.6' ("Unable to parse option value \".6\" as duration"):
        # every render with assets/music.* died in audio_mix before its first frame
        import math
        import struct
        import tempfile
        import wave

        def tone(path, seconds, hz, rate=48000):
            with wave.open(path, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * hz * i / rate)))
                                       for i in range(int(seconds * rate))))

        with tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(proj, 'assets'))
            tone(os.path.join(proj, 'assets', 'voice.wav'), 3, 220)
            tone(os.path.join(proj, 'assets', 'music.wav'), 1, 440)   # shorter than the reel: it loops
            out = os.path.join(proj, 'mix.wav')
            music = render.audio_mix(proj, {'reel_dur': 3.0, 'sfx': []}, out)
            self.assertTrue(music.endswith('music.wav'))
            with wave.open(out) as w:
                self.assertAlmostEqual(w.getnframes() / w.getframerate(), 3.0, places=1)


class RejectedSession(unittest.TestCase):
    def test_a_session_whose_browser_had_no_gsap_is_thrown_away(self):
        log = ('[FrameCapture:sub_timeline_script_failure] A sub-composition timeline script failed to load '
               '(https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js)\nFailed: Render blocked by 1 correctness warning')
        self.assertIn('GSAP', render.broken_session(log))
        self.assertIsNotNone(render.broken_session('Failed: Render blocked by 1 correctness warning'))
        self.assertIsNone(render.broken_session('[INFO] Inlined CDN script: gsap.min.js\n 229.5 MB · 150 frames · rendered in 58.9s'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
