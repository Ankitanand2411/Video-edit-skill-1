# Storyboard mode

A folder with raw clip(s) + a storyboard spreadsheet (.xlsx) -> the reel with the storyboard's pictures, supers and
end card laid on the edit. First built for "How handwriting helps the brain learn to read" (one 87s phone clip + a
5-scene storyboard -> a 68s reel).

## The spreadsheet (what storyboard.py reads)
- A header row naming the columns: `SCENE`, `STORYBOARD`, and optionally `REFERENCE` (any order, any position).
- One row per scene below it. The STORYBOARD cell holds labelled blocks:
  `VISUALS:` (one shot idea per line), `SUPER:` (on-screen text), `SCRIPT / VO:` (what the creator meant to say).
- A picture anchored in the scene's row (Excel: Insert > Picture > Place over cells, in that row) is the scene's
  visual. Several pictures in one row are kept in order.
- Optional above the table: a `BRAND` / `TITLE` cell with the title under it, a `MOOD` cell with the mood under it
  ("Color, Music, Pace: Vibrant, Inspirational, Medium, 1 min").
- Pictures are extracted byte-for-byte to `assets/storyboard/` (no re-encode). Reference pictures are often stock
  or AI images "for illustration purposes": tell the user they need the rights before posting.

## Pipeline
```
PY SK/scripts/storyboard.py <project> <storyboard.xlsx>    # storyboard.json + the pictures, untouched
... ingest, EDL, assemble, align, headpos as usual (the cutout comes after the build) ...
PY SK/scripts/storyboard_plan.py <project>                 # storyboard_plan.json: scenes, cutaways, supers, end card
```
The SCRIPT is the creator's intent, not what they said: use it to understand the reel and to check names and
keywords, but captions always follow the speech (edl.json lines). Takes and order still come from the clips.

## What the plan decides (then LOOK at every picture and fix what does not fit)
- **Scenes**: each scene's script is aligned to the spoken words (difflib over normalised tokens); a boundary goes on
  the first cut after the last word matched to the previous scene.
- **Cutaways** (one per scene picture): the picture as a card while the voice carries on, on the shot whose words
  best match the scene's VISUALS (first visuals line counts double; "kids" ~ "child", "write" ~ "written").
  Never in the first 2s; a long shot gets a 2.5-4.5s window around the matching words; a window that would leave
  under 1s of the speaker at either end snaps to the cut. Check: does the picture show what is being said?
  Move the window to the line it illustrates (e.g. a child tracing letters -> "all that tracing and scribbling").
- **Split screen**: VISUALS mention a split screen and the SUPER reads "A vs. B" -> the previous scene's picture (A)
  on top, this scene's (B) below, labels A / B, an italic accent "vs." between, timed to the speaker saying A ... B.
  The punch words for A and B are dropped (the labels say them); the captions are hidden for those ~3s.
- **Supers**: "W1 -> W2 -> W3" whose words are spoken -> a lower-third plate with the whole progression dimmed and
  each step lighting up (accent yellow) as it is said; any other SUPER (not the last scene's) -> a lower-third plate
  over the scene's last ~3s, last two words in the accent; the last scene's SUPER -> the end card.
- **End card**: the last scene's picture + its SUPER (one line per sentence, the last line italic accent), in at the
  last word + 0.8s (let the payoff word land), held 3s. The reel runs past the a-roll; the card covers the frame.

## Picture quality (the user will look for it)
- Pictures are cards, never full-bleed: filling 9:16 from a 3:2 picture means upscaling 1.4x-4x (soft). A card
  shows each picture at its native size or smaller: `fit()` never scales up (a 720x480 picture shows 720x480).
- `display_copy()` makes one Lanczos copy at the exact on-screen size; the browser then draws it 1:1. No tilt,
  no zoom, no push-in while it rests (cards sit outside #stage); the entrance tween clears its transform when done.
- The blurred backdrop behind a card is a blurred copy of the same picture (its own scale never shows).
- Render with `scripts/render.py` (PNG capture, one x264 encode at crf 12). HyperFrames' MP4 path captures JPEG.
- Verify on the final render: crop a card from a frame and compare it with its display copy (PSNR > 40 dB).

## Layout (1080x1920, inside the safe zone)
- Card: under the shot's caption line (caps_top + line height + 28), at most 960 wide, bottom at y <= 1140 (the
  right-hand icon column starts at y 1155); the punch word of that moment sits under the card, in front.
- Split: two 760-wide cards at y 236 and below a 150px gap; labels as pills inside the cards' top-left corners.
- Lower-third plates: top y 1398 (under the chin in a close-up), at most ~880 wide (the icon column), 26px tracked caps.
- End card: picture card at y 290, lines below it in the look's punch font, the last line italic accent.

## Mood
- "Vibrant / inspirational" with the cool dude look: keep the editorial grade but lift it (room brightness
  .80 -> .86, saturation .84 -> .92, subject saturation .86 -> .98); the warm pictures carry the colour.
- "Music": the skill has no music library. Ask the user for a track (royalty-free, theirs to use) and save it as
  `assets/music.mp3`; render.py loops it under the voice at -14 dB with sidechain ducking. Never invent a source.
- "1 min": a tight cut of the takes usually lands there; do not pad, do not cut lines to hit it.
