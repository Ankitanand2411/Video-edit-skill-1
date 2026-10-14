#!/usr/bin/env python3
"""Fetch the models once, robustly, so no edit ever stalls on a download: Whisper small.en (transcription and
per-shot alignment) and u2net_human_seg (HyperFrames' background removal, ~168 MB, verified against rembg's md5).

Usage:  PY models.py [--medium]      (--medium also fetches Whisper medium.en, ~1.5 GB, used by transcribe_cut.py)
Run by setup.py with the skill's own Python. Prints a STATUS line per model.
Slow or broken links: downloads go IPv4-first, and a mirror slower than ~150 KB/s is dropped for the next one
(GitHub release assets can crawl at ~40 KB/s on some networks; the Hugging Face mirror usually runs at MB/s).
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    skillenv.utf8_stdio()
    for name in ['small.en'] + (['medium.en'] if '--medium' in sys.argv else []):
        try:
            skillenv.whisper(name)
            print(f'STATUS whisper {name} OK', flush=True)
        except Exception as e:   # offline: the first transcription will try again
            print(f'STATUS whisper {name} MISSING ({str(e)[:120]}) -> check the internet connection and re-run setup', flush=True)
    u = skillenv.U2NET
    if os.path.isfile(u['path']) and md5(u['path']) == u['md5']:
        print('STATUS cutout model OK', flush=True)
    elif skillenv.download(u['urls'], u['path'], u['md5'], say=lambda s: print(s, flush=True)):
        print('STATUS cutout model OK (downloaded)', flush=True)
    else:
        print('STATUS cutout model MISSING -> the first cutout downloads it itself (slow links: re-run setup later)', flush=True)


if __name__ == '__main__':
    main()
