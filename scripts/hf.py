#!/usr/bin/env python3
"""HyperFrames launcher: one command that works the same in zsh, bash, Git Bash and PowerShell.

Usage (from the project folder):   PY hf.py <hyperframes arguments>
  PY hf.py lint
  PY hf.py snapshot --at 1.2,3.4,5.6 --no-end --describe false
  PY hf.py render -o renders/<slug>-v1.mp4 --quality high

Runs `npx --yes hyperframes@0.8.34 <arguments>` (the pinned version) with the Node 22+ that setup.py found first
on PATH, so there is no `nvm use`, and without a shell, so Windows' npx.cmd is not a problem. Standard library only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

def missing_media(page='index.html'):
    """cutout pieces (assets/subject/...) the page uses that are not there yet: HyperFrames would render the frame
    without them (best effort), the behind-head words then over the face"""
    if not os.path.isfile(page):
        return []
    with open(page, encoding='utf-8', errors='replace') as fh:
        srcs = re.findall(r'src="(assets/subject/[^"]+)"', fh.read())
    return [s for s in dict.fromkeys(srcs) if not os.path.isfile(s)]


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] in ('snapshot', 'render', 'preview'):
        page = sys.argv[sys.argv.index('-c') + 1] if '-c' in sys.argv else 'index.html'
        gone = missing_media(page)
        if gone:
            sys.exit(f'{len(gone)} cutout pieces not cut out yet ({gone[0]} ...): run cutout.py first')
    code = skillenv.run_hyperframes(sys.argv[1:])
    if code and sys.argv[1] == 'snapshot':   # a page that loads GSAP from the CDN can miss its 10 s navigation timeout
        print('snapshot failed once (often a slow network moment): trying again', flush=True)
        code = skillenv.run_hyperframes(sys.argv[1:])
    sys.exit(code)
