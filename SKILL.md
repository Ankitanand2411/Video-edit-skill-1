---
name: video-edit
description: "Turns raw 9:16 talking-head clips into a finished, premium Instagram reel end to end: picks the cleanest take of every line across your clips, cuts dead air, punches in, cuts you out of the background for words behind your head, applies one of three designed looks (bold kinetic words, cool girl, cool dude), lays a storyboard spreadsheet on the edit (its pictures as full-quality cutaways, its supers, an end card), builds animated UI inserts with parallel sub-agents, adds subtle sound design, renders losslessly and checks every cut frame by frame inside the Reels safe zone. Trigger with /video-edit or phrases like 'edit these clips', 'edit the video in this folder', 'here is the storyboard', 'cut this into a reel', 'make this reel look fire'."
---

# /video-edit

Raw clips in, finished reel out. The user never opens an editor: they review a phone copy and give notes.
A folder with the raw clip(s) and a storyboard (.xlsx) is enough to get the finished reel: see Storyboard mode.

Read before building: `references/looks.md` (the three looks, exact values), `references/layout.md` (safe zone,
placement, behind-head formula), `references/gotchas.md` (every trap already hit once). Read
`references/storyboard.md` when the folder has a storyboard, `references/overlays.md` when the script calls for an
animated insert.

Works on macOS, Linux and Windows. setup.py detects the machine at the start of every run and every command below
comes from that record, so never guess paths or shells: see "This machine" right after Step 0.

## Step 0: First-time setup (runs once)

`SK` is this skill's folder (the one holding this SKILL.md), as a full path. Usually `~/.claude/skills/video-edit`;
on Windows that is `C:/Users/<name>/.claude/skills/video-edit`.

Look for `SK/config.json`.

**If it exists:** load it (name, instagram handle, default look, folders), run the setup script exactly as in
step 3 below (a few seconds: it only checks, and repairs the environment after an update), read "This machine",
and go to Step 1 once it prints READY. The user never runs setup themselves: "edit these clips" is enough. If it
prints `STATUS gpu AVAILABLE`, ask the user once whether to install GPU support (as in step 3) before Step 1:
the cutout and Whisper then run on the GPU for every edit after. If it prints `STATUS skill NOT WHERE CLAUDE CODE
LOOKS` (the folder was unzipped somewhere like the Desktop, so /video-edit does not trigger), offer
`setup.py --link`: a link from ~/.claude/skills/video-edit to the folder, nothing copied.

**If it does not exist:**
1. Say: "Welcome to /video-edit! Let's get you set up. This takes about 2 minutes and only happens once."
2. Ask, in one message:
   - Your name (used on your Instagram profile insert)
   - Your Instagram handle (for your profile insert and to pull your reels for the orbit effect)
   - Default look: **bold** (kinetic words behind your head), **cool girl** (warm, yellow serif italic, your reels
     orbiting you) or **cool dude** (dark editorial, tracked caps + serif). Offer bold if they are unsure.
   - Where your raw clips usually land (default `~/Downloads`) and where projects should live (default `~/reel-edits`)
3. Run the setup script with whichever Python the machine has. Try these in order until one prints STATUS lines:
   `python3 "SK/scripts/setup.py"`, then `python "SK/scripts/setup.py"`, then `py -3 "SK/scripts/setup.py"`.
   (On Windows `python3` is often a Microsoft Store stub that prints "Python was not found": just try the next one.)
   None of them runs: Python is missing. Give the fix for their system and stop (Windows:
   `winget install --id Python.Python.3.12 -e`, Mac: `brew install python`, Linux: `sudo apt install python3 python3-venv`).
   Then read the STATUS lines:
   - ffmpeg / node / python venv MISSING: the line ends with the exact fix for THIS machine (winget on Windows,
     brew on Mac, apt on Linux). Give it to the user and stop until the script prints READY.
   - Windows: the user pastes the winget lines into their own PowerShell window (winget asks them to agree to its
     terms the first time), then quits Claude Code completely and reopens it, or the new programs are not found.
   - The script downloads the 6 sound effects itself. If it still reports them MISSING (offline), that is optional:
     the reel just has no SFX until they are added.
   - It also fetches the models (Whisper small.en, the background-removal model) IPv4-first with a mirror fallback,
     so no edit stalls on a download later. MISSING there is not fatal: the first transcription / cutout retries.
   - `STATUS gpu AVAILABLE` (an NVIDIA GPU, or any DirectX 12 GPU on Windows): ask the user once whether to install
     GPU support (one time, ~1.7 GB with NVIDIA, ~25 MB with DirectML, into the skill folder, no restart), then run
     `setup.py --gpu`. The cutout model then runs ~7x faster and Whisper 3-5x (GTX 1650: ~11 vs ~1.6 frames/s).
     Optional: everything works on the CPU without it. `STATUS gpu OK` says what runs where.
4. Optional, Apify (pulls reels and profile stats automatically): try a simple Apify MCP call. If it is not
   connected, say it is optional and how to add it:
   1. Create a free account at https://apify.com and copy the API token from Settings > API & Integrations.
   2. In a terminal, paste this one line with the token in place of YOUR_TOKEN:
      `claude mcp add apify -e APIFY_TOKEN=YOUR_TOKEN -- npx -y @apify/actors-mcp-server`
      (heads up: Claude Code stores the token in plain text in `~/.claude.json`; keep that file private).
   3. Reopen Claude and run /video-edit again.
   Without Apify, the skill asks them to drop their reel files into the project instead.
5. Save `SK/config.json` (no secrets, ever):
   ```json
   {"name": "...", "instagram": "handle-without-@", "defaultLook": "bold", "clipsDir": "~/Downloads",
    "projectsDir": "~/reel-edits", "setupComplete": true, "setupDate": "YYYY-MM-DD"}
   ```
6. Say: "Setup complete! Running /video-edit now..." and continue.

## This machine (read on every run)

Read `SK/.platform.json`, written by setup.py. It records the OS (`os`: macos, linux or windows), the CPU and the
exact commands for this computer:
- `PY` = its `python` value: the skill's own Python (`.venv/bin/python` on Mac and Linux,
  `.venv/Scripts/python.exe` on Windows). Run EVERY Python script of this skill with it, never a bare `python3`.
- `HF` = `PY "SK/scripts/hf.py"`: starts the pinned HyperFrames (`npx --yes hyperframes@0.8.34 ...`) with the
  right Node on any OS. No `nvm use`, no `npx.cmd` trouble.
- `cutout`: `CUDA` / `DML` (GPU support installed: scripts/matte.py, ~2 min a reel), `CoreML` (Apple Silicon:
  HyperFrames on the Apple GPU) or `CPU` (scripts/matte.py on every core: ~8 min a reel, the slow step; say so, run
  it in the background and keep going). Only the frames with something behind the head are cut out.
- `gpu`: the GPU card and what runs on it (`cutout`, `whisper`), or null.

setup.py rewrites this file on every run (Step 0), so it is always current. File missing, or `PY` no longer
exists: setup did not run or did not reach READY; run it as in Step 0.3 and follow its fix.

One command style that works in zsh, bash, Git Bash and PowerShell:
- Full paths in double quotes with forward slashes (fine on Windows too): `"PY" "SK/scripts/ingest.py" "<project>"`.
- In PowerShell (Windows without Git for Windows, or whenever the PowerShell tool is the one you have) put `&` in
  front: `& "PY" "SK/scripts/ingest.py" "<project>"`.
- One command per call. No `&&`, no `VAR=1 command`, no `~` inside arguments, no `source`, no `zsh`.
- `ffmpeg` and `ffprobe` are on PATH on every OS (setup checks it), so one-off ffmpeg commands are the same everywhere.

## Hard rules
1. Everything inside the Reels safe zone: top 220, bottom 450 (nothing below y 1470), sides 35, right 100 from y 1155.
2. Never cover the face with text or cards. Behind-head words show at least ~70% of each letter.
3. Captions say what was actually said: fix Whisper's mishearings of names and keywords ("Claude" often comes out
   as "cloud"/"claws", "skill" as "scale"). No em dashes in on-screen text. A caption never shows a word its shot
   does not contain: when a line's first or last words are not heard, the cut clipped them. Fix the cut; never give
   such words hand-made times in words.json.
4. British English in every word on screen (captions, punch words, supers you write, inserts): recognise, colour,
   centre, travelled, organisation; -ise, never -ize. Whisper spells the American way whatever the accent; the scripts
   convert what they write (transcript, words.json, the punch display text) and match words spelling-blind, so never
   change a line to the American spelling to get past check_edl.py or align.py. Names and brands keep their own
   spelling ("Center Parcs", "Pfizer"): when the conversion changes one, FIX in build.py puts it back. Vocabulary is
   not spelling: "math", "mom" and "apartment" stay as said. The storyboard's own text is never changed.
5. Sound effects subtle (template `SFX_GAIN = 0.75` of the base volumes), never louder than the voice.
6. Credit other creators on screen (@handle) whenever their reels appear. Real numbers on the user's own profile;
   anything else (commenters, chat history) is a generic placeholder, never a real person, never fabricated proof.
7. Prove cuts from the final render, not from snapshots.
8. Never delete the user's files. Originals are read, never modified.

## Workflow

### 1. Intake
- Clips: the files or folder the user names, else the newest video files in `clipsDir`. Create the project as
  `<projectsDir>/<short-slug>/` (when the user names a folder for the work, the project goes inside that folder).
  (`~` in config.json is the user's home folder, `C:/Users/<name>` on Windows. The skill's scripts expand it.)
- **Storyboard mode**: a `.xlsx` storyboard in that folder (or one the user attaches) -> read
  `references/storyboard.md`, copy it into the project and run `PY SK/scripts/storyboard.py <project> <file.xlsx>`
  (storyboard.json + its pictures, untouched). Read every scene and LOOK at every picture before cutting.
  An audio file in the folder (mp3/m4a/wav) is a music bed: copy it to `<project>/assets/music.<ext>`.
- Reference links (IG reels, Pinterest pins) for a style: download them and look at frames before designing anything
  (see overlays.md for how to fetch them).

### 2. Ingest
```bash
PY SK/scripts/ingest.py <project> <clips or folder> [--newest 5]
```
Look at `work/sheets.jpg` (setups and angles, source resolution) and read `transcript.txt` (per-clip lines, words
with times, speech map). With a storyboard, its SCRIPT shows the intended order and the names to spell right; the
captions still follow what was said.

### 3. Pick takes -> `<project>/edl.json`
- Rebuild the script from the takes: people repeat a line until it lands. Use the LAST complete clean take unless
  the user says otherwise ("the better section starts at 0:47" means one continuous take from there).
- In/out points from the speech map: start ~0.05-0.07s before the first word, end at the silence start after the
  last word. Kill dead air between sections and false starts; confirm short pauses with silencedetect before
  trimming (Whisper can invent a leading word at a cut, and it misses fast words like "So I was" before a pause:
  a fast burst before a pause is easy to misjudge, "So I was" was once taken for "So" and cut off a line).
- Two segments in a row from the same angle: alternate wide / close. Close-up zoom depends on the source: 1.9 from
  4K, 1.5 from 1080p, 1.35 from 720p (more is visibly soft). Keep the eye line level: choose cy so the eyes sit at
  the same y as in the wide (`cy = (eye_y_src - (0.5 - eye_y_wide) * h_src / zoom) / h_src` with eye_y as fractions);
  the cut then reads as a push towards the eyes and leaves wall space above the head for type.
- Ending: keep ~1s after the last word when the speaker holds a look (a reflective beat reads as an ending; it also
  gives the last punch word time to land). A sign-off spoken too quietly to be heard is cut (tell the user).
- `line`: exactly what is said in that segment, with punctuation, in British spelling (align.py uses it as the caption
  text; it converts anything left American, and the transcript is already British).
- Unsure words (keyword, CTA trigger): re-transcribe that snippet with medium.en and a prompt containing the names.
- Format: `[{"id": "s01", "clip": "c1", "in": 12.66, "out": 15.72, "zoom": 1.0, "cx": 0.5, "cy": 0.5, "line": "..."}]`
- Check it: `PY SK/scripts/check_edl.py <project>` (assemble.py runs it first and refuses an EDL that fails). Each
  shot is transcribed on its own: a line's first or last words that are said just outside the cut fail it, with the
  in/out point to use instead. Its DROPPED report prints what is said in every stretch the cut leaves out.
- Post the EDL to the user as a short table (line, shot, look per section) plus what was cut, in the DROPPED report's
  own words ("cut: 'So I was'", never your summary of it), and keep going; do not wait.

### 4. Assemble, align, head position
```bash
PY SK/scripts/assemble.py <project>          # check_edl first; aroll.mp4 (30fps CFR), segments.json, voice (normalised)
PY SK/scripts/align.py <project>             # words.json: per-shot word times; exit 1 if a cut clipped a line's ends
PY SK/scripts/headpos.py <project>           # headpos.json (head top per shot) for placement: 3 masks a shot, no cutout
PY SK/scripts/storyboard_plan.py <project>   # storyboard mode: storyboard_plan.json (scenes, cutaways, supers, end card)
```
assemble.py cuts the shots side by side into lossless intermediates and compresses the a-roll once (~1 min a reel).
headpos.py runs the cutout model on 3 frames a shot (seconds on a GPU, under a minute on a CPU), so placement no longer
waits for a cutout. The cutout itself comes after the build (step 6): only the frames where something sits behind the
head are cut out, and the build is what decides those.
On a machine with under 8 GB of RAM run one heavy job at a time (Whisper, cutout, render, snapshot each want
1-1.5 GB). Re-assembling later (new in/out points) means new cutout pieces: cutout.py notices and redoes them.

### 5. Inserts in parallel (as soon as the EDL is locked)
For each animated insert the script calls for (an app on screen, the profile follow on the CTA, a file scroll),
spawn a sub-agent in the background with the brief template in `references/overlays.md`: fixed size, fixed
duration, beats locked to the word times, transparent webm out. Keep building the main edit while they work.

### 6. Build
Copy `SK/assets/template/` into the project (build.py, hyperframes.json, package.json, assets/fonts with
metrics.json, assets/sfx). build.py reads everything the scripts wrote; set its CONTENT block:
- `LOOK`: `defaultLook` unless the user asks ("cool guy" = cool dude). One look for the reel.
- `PUNCH`: the word that carries each shot (~1 per shot, 2 on shots over ~4s), behind the head. Leave it empty for
  a first pass: `PY build.py --plan` prints automatic picks (storyboard words, numbers, phrase ends); review them,
  paste the good ones in and replace the weak ones. Italic for the final word of a thought.
- `IMPACT`: a number or year among the punch words that deserves the soft bass hit (or None).
- Cool girl only: `SCRIPT_PUNCH` (one punch word set in handwriting with a drawn underline, e.g. {'ugly handwriting'})
  and `SPARKLE` (None picks the ✦ words itself; `--plan` prints them).
- Storyboard mode: open storyboard_plan.json next to the pictures and fix any cutaway that does not illustrate its
  line (move a/b to that line's shot); the build places cards, split, plates and end card from it.
- Multi-look reels, the orbit, creator cards and the Instagram follow insert: borrow the functions from
  `SK/assets/examples/first-reel-build.py` (the first reel's build; its machinery is documented in its docstring).
- Iterate from the project folder: `HF lint` (0 errors), then `PY build.py --safe`, then
  `PY SK/scripts/cutout.py <project>` (in the background when it says it has many frames to do), then
  `HF snapshot --at <10-20 moments> --no-end --describe false -o snapshots/vN`. Read the contact sheets, fix layout,
  readability and safe zone. (`HF` picks the right Node by itself, so there is no `nvm use`.)
- The cutout: build.py writes work/cutout_plan.json, the frames where something sits behind the head (every frame in
  the cool dude look, which lights the cutout on its own) in pieces of up to 10 s, and its last line says how many
  pieces are not cut out yet. cutout.py cuts out only those, several at a time; pieces already done are kept and the
  model's masks are cached per frame, so a rebuild that moves a punch word costs seconds. Snapshots and render.py
  refuse to run while a piece is missing (the words would sit over the face). One piece per <video>: a frame without
  anything behind the head skips the cutout layer, ~40% less render time on that frame.
- `SMALL behind-head words` after a build: a high head in a close-up left no room above it. Move that punch word to a
  wider shot or set it in front, before cutting out and snapshotting.

### 7. Render and QA
```bash
PY build.py                                        # without --safe (grep the html: rgba(255,0,0,.28) must be 0)
PY SK/scripts/cutout.py <project>                  # only if build.py says pieces are missing
PY SK/scripts/render.py <project> <slug>-vN        # lossless: PNG frames, browsers in parallel, one x264 encode
PY SK/scripts/check_cuts.py <project> renders/<slug>-vN.mp4 --phone
```
render.py, not `HF render`: HyperFrames' MP4 path captures JPEG frames (a second lossy step) and its capture can
stall for good on machines under 8 GB of RAM. render.py hard-links every captured frame, restarts a stalled session
at the first missing frame, mixes voice + SFX (+ assets/music.* ducked under the voice) and encodes once (crf 12,
BT.709). It runs as many browsers side by side as the free RAM allows (~0.7 GB each, up to 10), has Chrome write its
lossless PNGs with the fast encoder (same pixels, ~35% less time a frame), encodes while it draws on machines over
8 GB, and prints a speed line (frames/s, browsers, what the browser drew on). Measured on a 7 GB laptop, 30 frames,
1 browser: 1246 ms a frame before, 816 with the fast PNGs, 385 on a frame without the cutout layer.
check_cuts.py reads every cut frame in one pass and makes the phone copy while it checks lip sync (~30 s).
Look at `work/cut_check.jpg` (make a bigger grid when it is too small to judge): every after-cut frame shows the
new shot cleanly. check_cuts.py also prints lip sync per shot against the original clip: it must say LIP SYNC OK. Check audio peaks (`volumedetect`, max around -2 to -5 dB) and the silence at section joins.
Storyboard pictures: crop a card from a render frame and compare it with its display copy (PSNR > 40 dB).

### 8. Deliver
Send the files in the chat (SendUserFile): the phone copy (720p) to watch, and the full-quality render when the user
wants to save or post it. Report in plain terms what changed and anything that needs the user's call (music,
picture rights, a cut sign-off). Keep every version in `renders/`; back up `assets/` + `segments.json` + the
EDL / words to `work/vN/` before re-assembling.

## Defaults that came out of real feedback (do not re-litigate)
- Change the grade and captions to create a look; do not replace the background with an AI-generated room.
- No film grain. Dark is fine, but keep the subject lit and skin from going red.
- Lead-in captions centred in front of the speaker read better than lines pinned to the left edge.
- Words behind the head are the signature move, but only when readable.
- Storyboard pictures are cards at native size or smaller over a blurred copy of themselves, never full-bleed
  upscales. Supers are lower-third plates; a stepped super lights up step by step as the words are said.

---
