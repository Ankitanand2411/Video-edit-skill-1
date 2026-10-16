#!/usr/bin/env python3
"""GPU support tests: which path each machine gets, the pip NVIDIA library folders, and the cutout engine's recipe
(matte.py) against HyperFrames' own formulas. Proven end to end on a GTX 1650 (Linux): cutout 0.97 -> 5.51 frames/s,
masks 63.7 dB GPU vs CPU. Run with the skill's venv Python (numpy + Pillow):   PY tests/test_gpu.py"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import gpu  # noqa: E402
import matte  # noqa: E402
import skillenv  # noqa: E402

try:
    import numpy as np
except ImportError:   # plain python3 without the venv: the recipe tests are skipped
    np = None


class Plan(unittest.TestCase):
    def test_each_machine_gets_its_path(self):
        card = {'name': 'NVIDIA GeForce GTX 1650', 'vram_mb': 4096, 'driver': '595.99.02'}
        self.assertEqual(gpu.plan('linux', card), 'cuda')
        self.assertEqual(gpu.plan('windows', card), 'cuda')
        self.assertEqual(gpu.plan('windows', None), 'dml')     # AMD / Intel: DirectML
        self.assertIsNone(gpu.plan('macos', None))             # HyperFrames already uses CoreML
        self.assertIsNone(gpu.plan('linux', None))

    def test_cuda_pins_are_the_proven_set(self):
        pk = gpu.packages('cuda')
        self.assertIn('onnxruntime-gpu==1.22.0', pk)            # 1.31 wants CUDA 13
        self.assertIn('nvidia-cudnn-cu12==9.10.2.21', pk)       # 9.27 failed on Turing
        self.assertIn('nvidia-cuda-nvrtc-cu12==12.9.86', pk)    # the CUDA provider needs libnvrtc
        self.assertEqual(gpu.packages('dml'), ['onnxruntime-directml==1.22.0'])
        self.assertEqual(gpu.packages(None), [])

    def test_nvidia_smi(self):
        self.assertEqual(gpu.parse_nvidia_smi('NVIDIA GeForce GTX 1650, 4096 MiB, 595.99.02\n'),
                         {'name': 'NVIDIA GeForce GTX 1650', 'vram_mb': 4096, 'driver': '595.99.02'})
        self.assertIsNone(gpu.parse_nvidia_smi(''))
        self.assertIsNone(gpu.parse_nvidia_smi('NVIDIA-SMI has failed because it could not communicate with the driver'))

    def test_engine_order_and_package_per_os(self):
        self.assertEqual(matte.gpu_order('windows', 'x64'), ['cuda', 'dml'])
        self.assertEqual(matte.gpu_order('linux', 'x64'), ['cuda'])
        self.assertEqual(matte.gpu_order('macos', 'arm64'), ['coreml'])
        self.assertEqual(matte.ort_package('linux', True), 'onnxruntime-gpu')
        self.assertEqual(matte.ort_package('windows', False), 'onnxruntime-directml')


class Libraries(unittest.TestCase):
    def test_pip_nvidia_folders(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('cublas', 'cudnn', 'cuda_nvrtc'):
                os.makedirs(os.path.join(root, 'nvidia', name, 'lib'))
                os.makedirs(os.path.join(root, 'nvidia', name, 'bin'))
            linux = skillenv.cuda_lib_dirs([root], windows=False)
            self.assertEqual([os.path.basename(os.path.dirname(d)) for d in linux], ['cublas', 'cuda_nvrtc', 'cudnn'])
            self.assertTrue(all(d.endswith('lib') for d in linux))
            self.assertTrue(all(d.endswith('bin') for d in skillenv.cuda_lib_dirs([root], windows=True)))
        self.assertEqual(skillenv.cuda_lib_dirs(['/nowhere']), [])

    def test_nvrtc_is_preloaded_before_the_provider_needs_it(self):
        order = skillenv.CUDA_PRELOAD
        self.assertLess(order.index('libnvrtc.so.12'), order.index('libcudnn.so.9'))


@unittest.skipIf(np is None, 'needs the venv (numpy, Pillow)')
class Recipe(unittest.TestCase):
    """matte.py must do what HyperFrames' inference.ts does"""
    def test_preprocess_matches_hyperframes_formula(self):
        frame = np.full((1920, 1080, 3), (200, 100, 50), np.uint8)   # flat colour: resizing cannot change it
        t = matte.preprocess(frame)
        self.assertEqual(t.shape, (1, 3, 320, 320))
        self.assertEqual(t.dtype, np.float32)
        mx = 200.0   # divide by the brightest value, then ImageNet mean / std
        for c, v in enumerate((200, 100, 50)):
            self.assertAlmostEqual(float(t[0, c, 10, 10]), (v / mx - matte.MEAN[c]) / matte.STD[c], places=5)

    def test_mask_is_min_max_of_the_first_plane_resized(self):
        out = np.zeros((1, 1, 320, 320), np.float32)
        out[0, 0, :, 160:] = 7.0                       # right half "person"
        m = matte.mask_of(out, 1080, 1920)
        self.assertEqual(m.shape, (1920, 1080))
        self.assertEqual(int(m[960, 10]), 0)
        self.assertEqual(int(m[960, 1070]), 255)

    def test_flat_output_does_not_divide_by_zero(self):
        m = matte.mask_of(np.ones((1, 1, 320, 320), np.float32), 64, 64)
        self.assertEqual(int(m.max()), 0)

    def test_compose_puts_the_mask_in_alpha(self):
        frame = np.full((4, 4, 3), 9, np.uint8)
        y = np.zeros((1, 1, 320, 320), np.float32)
        y[0, 0, :, :] = np.linspace(0, 1, 320, dtype=np.float32)[None, :]
        rgba = np.frombuffer(matte.compose(frame, y), np.uint8).reshape(4, 4, 4)
        self.assertTrue((rgba[..., :3] == 9).all())
        self.assertLess(int(rgba[0, 0, 3]), int(rgba[0, 3, 3]))

    def test_psnr(self):
        a = np.zeros((8, 8), np.uint8)
        self.assertEqual(matte.psnr(a, a), 99.0)
        self.assertLess(matte.psnr(a, a + 16), matte.SELFTEST_DB)


class Encoder(unittest.TestCase):
    def test_same_vp9_settings_as_hyperframes_best(self):
        a = matte.encoder_args('ffmpeg', 1080, 1920, 30, 'out.webm')
        for k, v in (('-crf', '12'), ('-cpu-used', '4'), ('-deadline', 'good'), ('-pix_fmt', 'yuva420p'),
                     ('-colorspace', 'bt709'), ('-metadata:s:v:0', 'alpha_mode=1'), ('-auto-alt-ref', '0')):
            self.assertEqual(a[len(a) - 1 - a[::-1].index(k) + 1], v, k)   # the output's (-pix_fmt also names the input)


if __name__ == '__main__':
    unittest.main(verbosity=2)
