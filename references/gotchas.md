# Gotchas (each one cost a render)

## Timing / sync
- ffmpeg concat -> 0.033s video start offset + VFR gaps -> remove-background outputs extra frames -> the cutout drifts
  (by 20s it lagged a few frames: two copies of the speaker on screen after a cut). assemble.py re-encodes with
  `setpts=N/30/TB -fps_mode cfr`; cutout.py asserts equal frame counts.
- `tl.set` at a rounded time fires one frame late: use `frame/30 - 0.002`.
- storyboard_plan.json rounds times to 3 decimals: a card hidden at 5.267 with the cut at 5.2647 stayed on the first
  frame of the next shot (caught by check_cuts, one frame). build.py snaps any cutaway / super edge within 10ms of a
  cut onto the cut.
- `hyperframes snapshot` seeks approximately at cut boundaries; it can show the next shot a frame early. Only frames
  extracted from the final render (`check_cuts.py`) prove a cut.
- When a segment's in-point is trimmed, every hard-coded word time after it shifts. Keep a `SHIFT` derived from
  segments.json and wrap later times in `S(t)` (see template) instead of retyping them.
- Whisper word starts can be ~0.1-0.3s off and it hallucinates a leading word at a cut. Confirm pauses with
  `silencedetect` (n=-40dB, d=0.08) before trimming dead air.
- On a whole 60s cut Whisper's word times drift 0.5-0.8s early by the end (words landed before their own shot, and
  caption lines broke into orphans like "MY" / "AND"). align.py transcribes shot by shot: every word anchored.
- Whisper drops fast words before a pause ("So I was" said in 0.3s, then a pause), and that cuts both ways. The
  first cool girl reel LOST "So I was": the 0.3s burst before the pause was taken for "So" alone, the in-point went
  after the pause, and align.py's "5/7 heard" for that shot was waved off as Whisper missing fast words (this very
  note, misread). The words were not in the shot; the caption even showed them, from hand-made times. A shot's
  first or last line words missing with nothing heard in their place is the cut, every time, until a transcription
  of the audio just outside the cut says otherwise. check_edl.py does exactly that before assembling (assemble.py
  refuses a failing EDL) and align.py exits 1 on it. Never hand-time words Whisper did not hear in their shot.

## Rendering
- HyperFrames' MP4 output captures frames as JPEG (q95 at --quality high, q80 on some paths) before encoding: a
  second lossy step that softens photos and type. scripts/render.py captures PNG (--format png-sequence) and encodes
  once with x264 (crf 12, BT.709 tags; convert RGB with out_color_matrix=bt709 or colours shift).
- Under 8 GB of RAM HyperFrames forces low-memory mode (1 screenshot worker, ~2.7 fps JPEG / ~1 fps PNG on CPU) and
  the capture stalls for good after a few hundred frames (537, then 169, then 348 on one 7 GB Linux box; a JS seek
  never returns). Not one bad frame: a fresh session passes the same frame. render.py renders in 150-frame sessions,
  hard-links each finished frame (HyperFrames deletes its work folder when it fails) and restarts at the first
  missing frame. Chunks of a composition come from `build.py --range A B` (a wrapper timeline: tl.tweenFromTo).
- A chunk rendered for a duration rounded to 3 decimals can carry one extra frame (the next chunk's first): keep
  exactly end - start frames per chunk when joining.
- `--format png-sequence` numbers frames from 0 in its work folder (captured-frames/frame_000000.png) and from 1 in
  the finished output folder (frame_000001.png). Mixing the two without the -1 put frame N-1's image in slot N at
  six session ends (visible 1-frame stutters). render.py treats a finished session's output folder as the authority.
- Puppeteer starts Chrome detached: killing the render process leaves chrome-headless-shell running (memory). Kill
  the Chrome PIDs that appeared after the session started. Never `pkill -f <pattern>` from a shell whose own command
  line contains the pattern: it kills that shell (happened twice).
- A cutout encoded with sparse keyframes (libvpx default: one every 128 frames) makes every seek decode up to 127
  frames of 1080x1920 VP9-alpha; -g 15 got a stalling chunk from 169 to 348 frames. Re-encode with -g 15 if renders
  stall early.
- CSS `-webkit-mask-image` does not survive the renderer. Bake alpha into a VP9 WebM with ffmpeg alphamerge instead.
- `autoAlpha:1` sets opacity to 1 and overrides a CSS `opacity` on the same element. A "3% grain" layer shown with
  autoAlpha ran at 100%. Put low opacity on an inner element or tween opacity to the target value.
- Every `<video>` needs an `id` or it renders frozen. Each overlapping media element needs its own `data-track-index`.
  `<audio>` SFX need ids too, and overlapping SFX need separate track indices (the template's lane allocator does it).
- Never tween autoAlpha/opacity on an element that has data-start (the framework forces opacity 1 on active clips):
  wrap it in a plain div and animate the wrapper.
- Lint rejects tweening letterSpacing (layout snapping): fake tracking with scaleX.
- Element ids cannot contain apostrophes ("i've" broke the whole inline script). Use keys like 'ive'.
- `fromTo` renders its from-state immediately: pass `immediateRender:false` for anything hidden until its time.
- Heavy backdrop-filter/blur on many elements can make captures go black; keep it to a few.
- Video start times: HyperFrames extracts a video's frames with `ffmpeg -ss <data-media-start>`, which drops a frame
  that starts even a hair before it. "17.967" (3 decimals, rounded up) lost the frame at 17.9667 s: a chunk restarted
  at frame 539 after a stall would have shown the a-roll a frame late. Write media starts a quarter frame early
  (template media_start()). It shows a video while start <= t <= start + duration (both ends): back-to-back videos
  end half a frame early, or the boundary frame shows both.
- Chrome's PNG encoder: a png-sequence render captures with optimizeForSpeed false (slow zlib). hf_fastpng.mjs
  (render.py preloads it into HyperFrames' Node) turns the fast encoder on: bit-identical frames, RGB and alpha,
  1246 -> 816 ms a frame. The speed line says "normal PNG capture" if a HyperFrames update moved what it patches.
- The cutout layer costs ~45% of a rendered frame (an RGBA PNG decoded and filtered every frame: 816 vs 447 ms).
  Where nothing sits behind the head it shows the a-roll's own pixels, so the template leaves it out there.
- Each render session downloads GSAP from the CDN while compiling. A DNS hiccup ("Failed to download CDN script ...
  fetch failed", then "sub_timeline_script_failure") fails that session: run it again.

## Speed (measured on a GTX 1650 laptop, 6 cores / 12 threads, 8 GB)
- One VP9 alpha encoder (crf 12, good, cpu-used 4) keeps ~6 threads busy: ~9.6 frames/s at 1080x1920, ~0.8 GB at
  its peak. Two side by side ~12 frames/s together, three slower (10). The cutout model: GPU ~15 frames/s, CPU
  1.6 (one thread per physical core; two sessions add ~13% and ~0.6 GB each: not worth it).
- `ffprobe -count_frames` decodes the whole file (~20 s for the a-roll and its cutout); `-count_packets` reads only
  the packets (one per frame in these files) in ~0.1 s.
- check_cuts: one ffmpeg per cut frame decoded the render up to that frame every time (38 decodes, ~70 s); one
  `select` over all of them is one pass.
- assemble: shots cut to lossless intermediates (x264 qp 0 ultrafast) side by side, then one crf 14 encode: a 6 s
  shot in 1.1 s instead of 5.2 s, and the a-roll is 0.9 dB closer to the original (one lossy pass, not two).

## Audio
- Lip sync drifted up to 0.67 s by the end of a 21-cut reel (v1 and v2 of the first storyboard reel): each segment's
  audio is up to a frame shorter than its video, and joined with the concat demuxer the gaps lived only in the
  timestamps. Any tool that decodes straight through (ffmpeg filter graphs, HyperFrames' audio mix) dropped them, so
  the sound ran ahead of the picture by ~30 ms more per cut. Seek-based checks (`-ss`) hid it. assemble.py now pads
  every segment's audio to its picture length and joins it losslessly (no timestamp gaps anywhere), and
  check_cuts.py measures lip sync per shot against the original clip with a straight-through decode.
- Every AAC pass costs fidelity, and a +16 dB loudness boost makes it audible: phone AAC -> cut -> voice -> mix -> phone
  copy measured 31 dB from the lossless mix; one pass at 320 kbps measured 45 dB. The voice stays lossless
  (assets/voice.wav) until render.py's single encode; the phone copy copies the audio instead of re-encoding it.
- FFT noise reduction (afftdn) did not lower the room tone of a boosted phone voice and shifted the audio: not used.
  The hiss that comes up with the boost is the recording's own (speech-to-noise stays ~30 dB); a closer mic fixes it.

## Assets / tools
- Networks with broken IPv6: Python downloads hang in SYN-SENT (Hugging Face's Xet client sat at 0 bytes, then the
  machine rebooted mid-download), while curl and Node fall back. skillenv.prefer_ipv4() sorts IPv4 first;
  skillenv.whisper() loads offline first and downloads without Xet. GitHub release assets can crawl at 20-70 KB/s:
  setup.py (models.py) fetches the cutout model from a faster mirror, verified against rembg's md5.
- onnxruntime-node's postinstall downloads ~400 MB of CUDA binaries from GitHub on Linux x64; at GitHub's slow speed
  it held the first cutout for 10+ minutes. skillenv sets ONNXRUNTIME_NODE_INSTALL_CUDA=skip for every HyperFrames run.
- Phone audio is often quiet (-34 LUFS, peaks -11 dB). assemble.py writes assets/voice.m4a with a two-pass linear
  loudnorm to -16.5 LUFS / -2 dB peaks; the build plays it instead of the a-roll's own track.
- Extending the reel's end after the cutout exists: re-assemble (the earlier frames are identical, PSNR ~55 dB), cut
  out only the new tail frames (`HF remove-background tail.mp4`), and splice: decode both with -c:v libvpx-vp9 (or
  the alpha is dropped), concat, encode yuva420p with -auto-alt-ref 0. Anything else changed means a full cutout.
- Fonts: the bundled woff2 are latin subsets with no arrow glyph (→ renders as a thin fallback dash). Draw arrows
  as inline SVG. assets/fonts/metrics.json has every font's ascent / descent / x-height / cap height / advances:
  compute widths and baselines from it instead of eyeballing.
- A GPU with its driver but no CUDA 12 runtime (a GTX 1650 without the toolkit): faster-whisper chose "cuda" and
  died mid-transcription with "libcublas.so.12 is not found". skillenv.whisper() uses the GPU only when cuBLAS and
  cuDNN load, the CPU otherwise.
- GPU cutout (scripts/matte.py, onnxruntime for Python, HyperFrames' recipe): HyperFrames 0.8.34 itself offers CUDA
  on Linux only (its Windows build ships DirectML but no way to pick it). The working set on a GTX 1650 (Turing,
  driver 595 / CUDA 13.2): onnxruntime-gpu 1.22 + CUDA 12 pip libraries + cuDNN 9.10. onnxruntime-gpu 1.31 wants
  CUDA 13 (libcublasLt.so.13); cuDNN 9.27 fails on Turing ("No valid engine configs for ConvFwd"); the CUDA provider
  also needs libnvrtc.so.12, which sits in its own pip folder (skillenv.CUDA_PRELOAD loads it first).
- onnxruntime re-creates a session on the CPU when a GPU kernel fails at run time and carries on silently: a "cuda"
  self-test compared the CPU with itself. matte.py calls session.disable_fallback() and checks the provider after the
  run. Whisper's own requirement re-installs the CPU-only onnxruntime over the GPU build on a venv repair: gpu.py
  (every setup run) notices and restores the GPU build from pip's cache (11 s).
- Our cutout vs HyperFrames' on the same frames: alpha 40 dB average, 146/150 frames >= 35 dB; the rest differ only
  inside the glasses lenses (both models leave them half see-through; the same frame sits under the cutout, so it
  does not show). The resizers differ (Pillow Lanczos vs sharp/libvips). GPU vs CPU of our engine: 63.7 dB.
- Parallel render: frames of several browsers live in `capture-attempt-*/worker-*/` while the render runs
  (`captured-frames/` stays empty): a watchdog that only looked there killed healthy renders.
- HyperFrames extracts an opaque video (the a-roll) as JPEG for the browser by default (`--video-frame-format auto`):
  a hidden lossy step on the background. render.py passes `--video-frame-format png`.
- Node 22+ for HyperFrames, pinned `hyperframes@0.8.34`. Start it with `HF` (`PY "SK/scripts/hf.py" <command>`): it
  puts a Node 22+ first on PATH on any OS (an nvm default of Node 20 otherwise gives "HyperFrames requires Node.js >= 22").
- Python scripts run in the skill's own venv. Its path differs per OS (`.venv/bin/python` on Mac and Linux,
  `.venv/Scripts/python.exe` on Windows), so read `python` from `SK/.platform.json` instead of typing it.
  The first transcription downloads the Whisper model (small.en ~0.5GB, medium.en ~1.5GB).
- Transcription dies with `open() got an unexpected keyword argument 'metadata_errors'`: the venv has PyAV 19, which
  faster-whisper 1.2.1 does not support. Run `scripts/setup.py` again (or the old `scripts/setup.sh`, which calls it);
  it pins `av<19` and repairs the venv.
- zsh: `for x in "a b"; do set -- $x` does not split; use `${=x}` or a Python loop.
- If a shell safety hook blocks inline heredoc scripts or moves into the Trash, write the script to a file and run
  it; download temp files into a scratch folder instead of moving things around. Never delete the user's files.
- Large file uploads to chat can fail: deliver a 720p crf 26-28 phone copy and keep the full render on disk.
- Pinterest/Instagram pages block logged-out browsing; curl the page HTML or use Apify.

## Windows (same skill, different shell)
- Claude Code on Windows runs commands in Git Bash when Git for Windows is installed, otherwise in PowerShell, and
  both can be available at once. Write commands that work in both: full paths in double quotes with forward
  slashes, one command per call, no `&&`, no `VAR=1 cmd`, no `~` in arguments. In PowerShell start a quoted program
  with `&`: `& "PY" "SK/scripts/assemble.py" "<project>"`.
- `python3` is usually a Microsoft Store stub ("Python was not found"). Use `PY` for everything. Before the venv
  exists, try `python`, then `py -3`.
- A program installed while Claude Code is open is not found until Claude Code is fully quit and reopened (it keeps
  the PATH it started with). setup.py says so when it sees ffmpeg installed but not visible.
- `npx` is `npx.cmd` there: Python cannot start it by bare name. `HF` and cutout.py start it through node directly.
- HyperFrames' own cutout has no GPU path on Windows (CoreML on Apple Silicon only, CUDA only with
  `HYPERFRAMES_CUDA=1` and a CUDA build of onnxruntime). The skill's matte.py does it instead: CUDA or DirectML after
  `setup.py --gpu`, every CPU core otherwise. On the CPU it is the slow step: run it in the background.
- Windows opens text files as cp1252 unless told otherwise: every `open()` in build.py needs `encoding='utf-8'`,
  or accents, curly quotes and emoji in captions come out broken (the page says charset UTF-8).
- File paths inside an ffmpeg FILTER (subtitles=, movie=, a fonts file) need the drive colon and backslashes
  escaped (`C\:/Users/...`). Pass files with `-i` instead; the skill's scripts never put a path in a filter, and the
  concat list holds bare file names only.
- Git Bash rewrites arguments that start with `/` into Windows paths. Fine for file paths; for anything else
  (a `/flag`) set `MSYS_NO_PATHCONV=1` for that command.
- Smart App Control (Windows 11) can block the unsigned image library (sharp) that HyperFrames loads for snapshots
  (the cutout loads the same library); antivirus can make ffmpeg fail once with `spawn EBUSY`. Retry once, then
  tell the user what Windows blocked.
- Windows on ARM (Snapdragon): the transcription engine has no ARM build; setup.py asks for the x64 Python.
