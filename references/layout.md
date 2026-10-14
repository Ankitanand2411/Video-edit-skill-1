# Layout rules (1080x1920)

## Instagram Reels safe zone (HARD)
- Top 220px clear (IG header).
- Bottom 450px clear: nothing below **y = 1470** (username, caption, audio row).
- 35px clear on the left and right.
- Right 100px column clear from **y ~1155** down (like / comment / share icons).

Check it, do not eyeball it: `PY build.py --safe` draws the unsafe area in red (see `SAFE_GUIDE` in the template), snapshot 10-20 moments with it on, fix, then build WITHOUT it for the render (grep the html for `rgba(255,0,0,.28)` -> must be 0).

## Where things go
- Lead-in caption lines: centred, chest band (y ~950-1300), in front of the speaker. Fine to sit over the body; never over the face (eyes to chin).
- Punch words: behind the head near the top, or big over the chest.
- Cards/windows (UI recreations, creator reels): scale them so the bottom edge ends at y <= 1470. A card "under the face" starts below the chin (measure with headpos.py). A window "behind" the speaker sits on the wall with their head overlapping its bottom ~80px.
- Creator reel cards: 260x462 tiles, white border, slight tilt (-7 / +6 deg), beside the face, @handle pill under each (always credit them).

## Behind-head words (readability formula)
Use `headpos.json` (scripts/headpos.py) for the head top during the word; the template interpolates it in time.
Compute from the punch font's real metrics (assets/fonts/metrics.json), not a rule of thumb:
- A block of line-height LH puts the baseline at `top + k*S`, `k = (LH + ascent - descent) / 2`
  (DM Serif Display at 1.12: k = .91; Inter Tight 900 at .9: k = .81; Instrument Serif italic at 1.0: k = .84).
- Target: baseline = head top + 0.2 * x-height * S, so the hair covers at most the bottom fifth of the lowercase:
  `top = head_top + (0.2 * xh - k) * S`  (DM Serif: top = head_top - .81 S).
- The caption line above must clear the ascenders (~1.05 * cap height above the baseline) by ~24px; when the head is
  high (close-ups, leaning in) shrink S rather than push the caption above y 228.
- Width: sum of the advances (+ tracking) * S must stay under ~960px.
The old `.72 * S` rule assumed line-height .9 and sank DM Serif words ~35px into the hair ("li_es", "typ_g").
If the head moves a lot during the word (leaning in), put the word in front over the chest instead.

## Cut timing
Cut times = first frame of each segment from segments.json: `frame/30 - 0.002`. The 2ms nudge makes a `tl.set` land ON the first frame of the new shot (without it, float rounding fires it one frame late and the next shot shows the old shot's overlays for a frame).
