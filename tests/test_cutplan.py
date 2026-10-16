#!/usr/bin/env python3
"""Cutout only where something sits behind the head: the template's plan (which frames, which pieces, frame-exact
video timing), cutout.py's bookkeeping, headpos from masks, and the guards that stop a render with pieces missing.
Measured on the handwriting reel (girl look): 775 of 1936 frames in 15 pieces; a rendered frame without the cutout
385 vs 637 ms; renders with and without the pieces 42-46 dB apart (compression noise on the person only).
Run with the skill's venv Python (numpy + Pillow):   PY tests/test_cutplan.py"""
import ast
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import cutout  # noqa: E402
import hf  # noqa: E402
import render  # noqa: E402
import skillenv  # noqa: E402

try:
    import numpy as np
    import headpos
except ImportError:   # plain python3 without the venv
    np = headpos = None

NAMES = {'CUT_MARGIN', 'CUT_MERGE', 'CUT_PIECE', 'FPS', 'NOT_ZERO', 'ZERO', 'html_ids', 'hides', 'shown_windows',
         'cut_pieces', 'piece_file', 'floor6', 'media_start', 'cut_videos'}


def template():
    """the plan functions of assets/template/build.py, without running the build (it reads a project)"""
    src = open(os.path.join(ROOT, 'assets', 'template', 'build.py'), encoding='utf-8').read()
    keep = []
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(n.id in NAMES for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)):
            keep.append(node)
    ns = {'re': re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), 'build.py', 'exec'), ns)
    return ns


T = template()

PUNCH = ['<div id="s3" class="pw it" style="top:450px">handwriting</div>',
         '<div id="sp1" class="spark" style="left:264px;z-index:3">&#10022;</div>']
TWEENS = ["gsap.set('#s3',{autoAlpha:0});",
          "tl.fromTo('#s3',{autoAlpha:0,y:22,scale:.92},{autoAlpha:1,y:0,scale:1,duration:.4,ease:'power2.out',immediateRender:false},15.373);",
          "tl.set('#s3',{autoAlpha:0},16.098);",
          "gsap.set('#sp1',{autoAlpha:0,scale:0});",
          "tl.fromTo('#sp1',{autoAlpha:0,scale:0,rotation:-40},{autoAlpha:1,scale:1,rotation:0,duration:.32,immediateRender:false},10.357);",
          "tl.to('#sp1',{scale:.68,duration:.38,yoyo:true,repeat:1,ease:'sine.inOut'},10.677);",
          "tl.to('#sp1',{autoAlpha:0,duration:.14},11.807);",
          "tl.set('#sp1',{autoAlpha:0},11.947);",
          "tl.set('#c2',{autoAlpha:0},3.0);"]


class Windows(unittest.TestCase):
    def test_from_first_show_to_last_hide(self):
        w = T['shown_windows'](T['html_ids'](PUNCH), TWEENS, 66.0)
        self.assertEqual(set(w), {'s3', 'sp1'})
        self.assertAlmostEqual(w['s3'][0], 15.373)
        self.assertAlmostEqual(w['s3'][1], 16.098)
        self.assertAlmostEqual(w['sp1'][0], 10.357)
        self.assertAlmostEqual(w['sp1'][1], 11.947)

    def test_never_too_little(self):
        # shown from the start (no hiding gsap.set), never hidden again, or no tweens at all: the whole reel
        w = T['shown_windows'](['a', 'b', 'c'], ["tl.to('#a',{autoAlpha:0,duration:.2},5.0);",
                                                 "gsap.set('#b',{autoAlpha:0});", "tl.to('#b',{autoAlpha:1,duration:.3},4.0);"], 60.0)
        self.assertEqual(w['a'], (0.0, 5.2))
        self.assertEqual(w['b'], (4.0, 60.0))
        self.assertEqual(w['c'], (0.0, 60.0))
        self.assertNotIn('d', T['shown_windows'](['d'], ["gsap.set('#d',{autoAlpha:0});"], 60.0))   # never shown

    def test_half_opacity_is_not_hidden(self):
        self.assertFalse(T['hides']("tl.to('#a',{autoAlpha:0.5},1);"))
        self.assertFalse(T['hides']("tl.to('#a',{opacity:0,autoAlpha:1},1);"))
        self.assertTrue(T['hides']("tl.set('#a',{autoAlpha:0,y:0},1);"))


class Pieces(unittest.TestCase):
    def test_margin_merge_and_split(self):
        p = T['cut_pieces']([(1.0, 2.0), (2.2, 3.0), (10.0, 30.0)], 1936)
        self.assertEqual(p[0], (27, 93))                       # 1.0-3.0 s (gap of 6 frames closed) +- 3 frames
        self.assertTrue(all(b - a <= 300 for a, b in p))       # long stretches split for parallel cutting
        self.assertEqual(sum(b - a for a, b in p[1:]), 900 - 300 + 6)
        self.assertEqual(p[-1][1], 903)

    def test_clipped_to_the_a_roll(self):
        self.assertEqual(T['cut_pieces']([(63.9, 70.0)], 1936), [(1914, 1936)])
        self.assertEqual(T['cut_pieces']([(65.0, 70.0)], 1936), [])

    def test_every_frame_look(self):
        p = T['cut_pieces']([(0.0, 64.533)], 1936, margin=0)
        self.assertEqual((p[0][0], p[-1][1]), (0, 1936))
        self.assertEqual(sum(b - a for a, b in p), 1936)


class VideoTiming(unittest.TestCase):
    """HyperFrames shows a video while start <= t <= start + duration and uses frame floor((t - start) * fps + 1e-9);
    its extraction (`ffmpeg -ss <media start>`) drops frames that start before the media start"""

    def frames_shown(self, tag, fps=30, n=200):
        start = float(re.search(r'data-start="([\d.]+)"', tag).group(1))
        dur = float(re.search(r'data-duration="([\d.]+)"', tag).group(1))
        ms = float(re.search(r'data-media-start="([\d.]+)"', tag).group(1))
        first_media = next(k for k in range(10000) if k / fps >= ms)   # the first frame extraction keeps
        out = {}
        for f in range(n):
            t = f / fps
            if start <= t <= start + dur:
                out[f] = first_media + int((t - start) * fps + 1e-9)
        return out

    def test_every_frame_from_exactly_one_piece(self):
        pieces = [(48, 68), (68, 90), (98, 150)]
        for a0, length in ((0.0, 200), (2.0, 120), (69 / 30, 100)):
            tags = T['cut_videos'](pieces, a0, length / 30)
            f0 = round(a0 * 30)
            seen = {}
            for tag in tags:
                a = int(re.search(r'subject/(\d+)-', tag).group(1))
                for f, k in self.frames_shown(tag).items():
                    self.assertNotIn(f, seen, f'chunk {f0}: frame {f + f0} shown twice')
                    seen[f] = a + k
            want = {f - f0: f for a, b in pieces for f in range(max(a, f0), min(b, f0 + length))}
            self.assertEqual(seen, want)

    def test_a_roll_media_start_lands_on_its_frame(self):
        for f in (0, 150, 537, 538, 539, 1900):
            ms = float(T['media_start'](f))
            self.assertEqual(next(k for k in range(3000) if k / 30 >= ms), f)


class CutoutBookkeeping(unittest.TestCase):
    def test_todo(self):
        plan = [{'a': 0, 'b': 10, 'file': 'x/0'}, {'a': 10, 'b': 20, 'file': 'x/1'}, {'a': 20, 'b': 30, 'file': 'x/2'},
                {'a': 30, 'b': 40, 'file': 'x/3'}]
        done = {'x/0': {'aroll': 'k', 'frames': 10}, 'x/1': {'aroll': 'old', 'frames': 10}, 'x/2': {'aroll': 'k', 'frames': 10}}
        frames = {'x/0': 10, 'x/1': 10, 'x/2': 9}
        need = cutout.todo(plan, done, 'k', lambda f: f in frames, lambda f: frames[f])
        self.assertEqual([p['file'] for p in need], ['x/1', 'x/2', 'x/3'])   # other a-roll, short, missing

    def test_engine(self):
        self.assertEqual(cutout.choose_engine([], 'macos', 'arm64'), 'hyperframes')   # the Apple GPU (CoreML)
        self.assertEqual(cutout.choose_engine([], 'windows', 'x64'), 'ours')
        self.assertEqual(cutout.choose_engine([], 'linux', 'x64'), 'ours')
        self.assertEqual(cutout.choose_engine(['--engine', 'hyperframes'], 'linux', 'x64'), 'hyperframes')


class Guards(unittest.TestCase):
    def test_snapshot_and_render_refuse_missing_pieces(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'assets', 'subject'))
            os.makedirs(os.path.join(d, 'work'))
            open(os.path.join(d, 'assets', 'subject', '00010-00020.webm'), 'w').close()
            page = os.path.join(d, 'index.html')
            with open(page, 'w') as fh:
                fh.write('<video src="assets/subject/00010-00020.webm"></video><video src="assets/subject/00030-00040.webm">')
            cwd = os.getcwd()
            try:
                os.chdir(d)
                self.assertEqual(hf.missing_media('index.html'), ['assets/subject/00030-00040.webm'])
            finally:
                os.chdir(cwd)
            with open(os.path.join(d, 'work', 'cutout_plan.json'), 'w') as fh:
                fh.write('{"pieces": [{"a": 10, "b": 20, "file": "assets/subject/00010-00020.webm"},'
                         ' {"a": 30, "b": 40, "file": "assets/subject/00030-00040.webm"}]}')
            self.assertEqual(render.missing_pieces(d, lambda f: 10), ['assets/subject/00030-00040.webm'])
            self.assertEqual(render.missing_pieces(d, lambda f: 9), ['assets/subject/00010-00020.webm',
                                                                     'assets/subject/00030-00040.webm'])
            self.assertEqual(render.missing_pieces(tempfile.gettempdir()), [])   # no plan: an older build


@unittest.skipIf(headpos is None, 'needs the venv (numpy, Pillow)')
class HeadPos(unittest.TestCase):
    def test_samples_stay_inside_the_shot(self):
        p = headpos.sample_frames([{'id': 's1', 'frame': 0, 'frames': 65}, {'id': 's2', 'frame': 65, 'frames': 2}])
        self.assertEqual(p['s1'], [13, 32, 52])
        self.assertTrue(all(65 <= f <= 66 for f in p['s2']))

    def test_measure(self):
        a = np.zeros((1920, 1080), np.uint8)
        a[600:, 300:800] = 255     # body from y 600
        a[400:600, 400:700] = 255  # head from y 400
        top, x0, x1, body = headpos.measure(a)
        self.assertEqual(top, 400)
        self.assertTrue(396 <= x0 <= 404 and 696 <= x1 <= 704)
        self.assertEqual(body[1], 400)
        self.assertIsNone(headpos.measure(np.zeros((1920, 1080), np.uint8)))


class Whisper(unittest.TestCase):
    def test_gpu_failure_redoes_the_call_on_the_cpu(self):
        calls = []

        class Model:
            def __init__(self, device):
                self.device = device

            def transcribe(self, audio, **kw):
                calls.append(self.device)
                if self.device == 'cuda':
                    def boom():
                        raise RuntimeError('CUDA failed with error out of memory')
                        yield
                    return boom(), 'info'   # faster-whisper fails while iterating, not at the call
                return iter(['seg']), 'info'

        real = skillenv._whisper_model
        skillenv._whisper_model = lambda name, kw: Model(kw['device'])
        try:
            w = skillenv.Whisper('small.en', {'device': 'cuda'})
            segs, info = w.transcribe('x.wav')
            self.assertEqual((segs, w.device, calls), (['seg'], 'cpu', ['cuda', 'cpu']))
            self.assertEqual(w.transcribe('y.wav')[0], ['seg'])   # stays on the CPU
            self.assertEqual(calls[-1], 'cpu')
        finally:
            skillenv._whisper_model = real

    def test_physical_cores(self):
        n = skillenv.physical_cores()
        self.assertTrue(1 <= n <= (os.cpu_count() or 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
