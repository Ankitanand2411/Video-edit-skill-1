# Storyboard mode

A folder with raw clip(s) + a storyboard spreadsheet (.xlsx) -> the reel with everything the storyboard asks for laid
on the edit: its pictures, the graphics its VISUALS describe, its supers and its closing frame. First built for "How
handwriting helps the brain learn to read" (one 87s phone clip + a 5-scene storyboard with pictures -> a 68s reel),
then for "Is Malaysia's under-16 social media ban enough?" (one 145s clip + a 5-scene storyboard with NO pictures,
only described graphics, + loose logos in the folder -> a 2 min news reel).

**Follow the storyboard: every VISUALS line ends up on screen, or is explicitly a camera note.** The under-16 reel's
first cut (v1) put none of its graphics on screen: the skill only understood pictures, so the phone with a
RESTRICTED stamp, the banned-vs-allowed split, the flowchart, the stat card, the map and the "Follow School Advisor"
closing frame were all skipped, and the folder's logos turned into full-screen photo cutaways instead. The version the
team wanted (v2) took several rounds of prompts. storyboard_plan.py now prints a coverage list (every VISUALS line and
what carries it) and render.py refuses to start while a planned graphic is not built.

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
- Loose pictures next to the spreadsheet (logos, photos: "roblox logo.jpg", "minecraft image.jpg") are copied
  byte-for-byte to `assets/storyboard/folder/` and listed in storyboard.json `folder_images` with names from their file
  names ("roblox logo" -> names ["roblox"], kind logo). Run storyboard.py on the spreadsheet where the user left it,
  so it finds them. A file whose name says nothing ("images logo.png") gets no names: LOOK at it and write its names
  in (the under-16 folder's "images logo.png" was the Minecraft wordmark). Graphics use them for the names they show;
  the user's own logo beats the bundled icon.

## Pipeline
```
PY SK/scripts/storyboard.py <project> <storyboard.xlsx>    # storyboard.json + the pictures (its own and the folder's), untouched
... ingest, EDL, assemble, align, headpos as usual (the cutout comes after the build) ...
PY SK/scripts/storyboard_plan.py <project>                 # storyboard_plan.json: scenes, graphics, cutaways, supers, end card,
                                                           # and the coverage list: every VISUALS line and what carries it
```
The SCRIPT is the creator's intent, not what they said: use it to understand the reel and to check names and
keywords, but captions always follow the speech (edl.json lines). Takes and order still come from the clips.

## VISUALS that describe a graphic (scripts/sbgraphics.py, drawn by the template's graphics layer)
A VISUALS line is read as one graphic ("Split-Screen Graphic:" with "Left Side..." / "Right Side..." lines under it is
one graphic; a "Transition Graphic:" line changes the graphic before it). Kinds, and how the under-16 reel used them:

| kind | VISUALS that read as it | on screen | timed to |
|---|---|---|---|
| stamp | an overlay / icons / banner / badge / lock ("a smartphone showing locked TikTok, IG, Facebook icons with a red "RESTRICTED" banner") | a phone of app tiles, a stamp banner slammed across it, lock badges; a Transition line flips the banner ("UNRESTRICTED: Gaming Platforms" + a gamepad, the phone glows green) | the banner on its word ("restricted"), the flip on its words ("gaming platforms") |
| split | split screen / Left vs Right / A vs. B | two panels (BANNED red, ALLOWED green chip), each side's icons, a VS disc, the red side's badge stamped on ("UNDER 16 BAN") with locks, the other's blinking ("⚠ NO REGULATION") | each icon as its platform is named; the second panel with its first name |
| flow | flowchart / process / steps / A ➔ B ➔ C | a numbered list, dim, each step lighting up yellow (the last one red when it is the harm: radicalisation, abuse...) | each step on its words (keyword in order; "Radicalisation / Exploitation" lit on "extremist") |
| stat | stat / callout / counter with a number ("100,000 Malaysian Kids") | the number rolling up digit by digit, its label, its note, the source on a chip with the year said ("UNICEF STUDY · 2022") | the number lands as it is said; the panel comes in on the source ("A UNICEF study...") |
| map | map | the named countries from a world map (Natural Earth 1:110m), lighting up as named, chips with their names, lines out to the named platforms' tiles | each country / platform on its word |
| cta | closing frame / end card / CTA ("Follow School Advisor for more education news") | the end card: the verb in a yellow pill (tapped), the name, the tagline | the last word + 0.8s |
| shot | close-up / b-roll / footage / camera directions | nothing: an edit note | |
| custom | anything else | a transparent insert built by a sub-agent (references/overlays.md) as `assets/graphics/<id>.webm` | the scene |

- Names in a graphic (TikTok, Instagram, Discord, Roblox...) get the bundled icon on its brand colour
  (`assets/icons`, Simple Icons, CC0) or the folder's logo / photo; a name with neither prints "no picture for": ask
  the user for its logo or leave the initials tile. Logos appear only where the storyboard names the platform.
- Every word a graphic shows is the storyboard's, exactly as written ("In-Game Chat (Roblox)", "Under 16 Ban",
  "UNICEF Study · 2022", "for more education News"): case and spelling untouched. A label the storyboard does not
  give comes from the speech ("How they do it" from "They do it by...").
- LOOK at `PY storyboard_plan.py` output: every graphic's beat times, the coverage list, the unused folder pictures.
  Change a time or a text in storyboard_plan.json when a beat is on the wrong word; the build follows it.

## On-screen text follows the storyboard (every video)
The storyboard is the source of truth for every word on screen:
- Captions: build.py aligns the spoken words to the SCRIPT (in order, spelling-blind) and shows each matched word as
  the script writes it: capitals ("Sounds like", "Malaysia's former Deputy Police Chief", "MCMC"), spelling
  ("radicalization" when the script says so), numbers ("100,000"). Words the script does not have show as the EDL line
  writes them. The under-16 reel: 240 of 267 spoken words matched. A lower-case look no longer lowercases a storyboard
  reel; an all-caps look (cool dude captions) stays all caps.
- SUPERs, split labels, badges, banners, steps, stat labels, place names and the closing frame: exactly as written
  (the plates drop the wide caps tracking when the SUPER is in mixed case). Emojis become icons, em dashes commas.
- PUNCH words in storyboard mode show the script's form of their words; build.py flags one that does not.
- MOOD: "Vibrant / bright" lifts saturation and brightness a touch, "moody / dark / serious" lowers them; its pace sets
  the breath between sentences in the cut.

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
  each step lighting up (accent yellow) as it is said; any other SUPER -> a lower-third plate where its words are said
  ("POLICE WARNING" on "police chief warned", "MCMC REVIEW" on "MCMC"), else over the scene's last ~3s, last two words
  in the accent. Its emoji becomes a small icon in front (🚫 ⚠️ 🎮 🎯 📱 ✅ ❌ 🔒; the fonts have none), an em dash a
  comma. The last scene's SUPER is the end card, unless its VISUALS describe a closing frame: then it is a plate too.
- **End card**: the closing frame's CTA (Follow pill, name, tagline) when the last scene's VISUALS describe one, else
  the last scene's picture + its SUPER (one line per sentence, the last line italic accent); in at the last word +
  0.8s (let the payoff word land), held 3s. The reel runs past the a-roll; the card covers the frame.

## Picture quality (the user will look for it)
- Pictures are cards, never full-bleed: filling 9:16 from a 3:2 picture means upscaling 1.4x-4x (soft). A card
  shows each picture at its native size or smaller: `fit()` never scales up (a 720x480 picture shows 720x480).
- `display_copy()` makes one Lanczos copy at the exact on-screen size; the browser then draws it 1:1. No tilt,
  no zoom, no push-in while it rests (cards sit outside #stage); the entrance tween clears its transform when done.
- The blurred backdrop behind a card is a blurred copy of the same picture (its own scale never shows).
- Render with `scripts/render.py` (PNG capture, one x264 encode at crf 12). HyperFrames' MP4 path captures JPEG.
- Verify on the final render: crop a card from a frame and compare it with its display copy (PSNR > 40 dB).

## Layout (1080x1920, inside the safe zone)
- Graphics: dark panels in the wall space above the head, 940 wide from y 236, the speaker in view underneath; one
  at a time. A graphic that would reach the hair is scaled down (build.py prints TIGHT under .62: frame those shots
  wider; close-ups under graphics at zoom 1.3 or less). While a reel has graphics the running captions sit under the
  face (y 1240 wide / 1310 close, above the plates at 1398) and no punch word goes up while a graphic is on screen.
- Card: under the shot's caption line (caps_top + line height + 28), at most 960 wide, bottom at y <= 1140 (the
  right-hand icon column starts at y 1155); the punch word of that moment sits under the card, in front.
- Split: two 760-wide cards at y 236 and below a 150px gap; labels as pills inside the cards' top-left corners.
- Lower-third plates: top y 1398 (under the chin in a close-up), at most ~880 wide (the icon column), 26px tracked caps.
- End card: picture card at y 290, lines below it in the look's punch font, the last line italic accent.

## Mood
- "Pace: Medium": sentences get a short breath between them (~0.3-0.5s: the out-point ~0.25s after a sentence's last
  word, the next in-point ~0.07s before its first); "fast" trims to ~0.15s, "slow" lets ~0.7s through. A reel never
  opens on silence (check_edl.py fails a first shot with more than 0.45s before its first word). "2 min": the length
  the cut lands on is what it is (the under-16 reel: 1:58 + the end card).
- "Vibrant / inspirational" with the cool dude look: keep the editorial grade but lift it (room brightness
  .80 -> .86, saturation .84 -> .92, subject saturation .86 -> .98); the warm pictures carry the colour.
- "Music": the skill has no music library. Ask the user for a track (royalty-free, theirs to use) and save it as
  `assets/music.mp3`; render.py loops it under the voice at -14 dB with sidechain ducking. Never invent a source.
- "1 min": a tight cut of the takes usually lands there; do not pad, do not cut lines to hit it.
