# Skill - 1

## What This Skill Does

Video Edit turns raw vertical talking-head clips into a finished Instagram Reel. It selects the strongest take of each line, removes pauses, creates punch-ins from high-resolution footage, adds captions and motion graphics, and produces a phone-ready video for review.

Use it when you have recorded several takes of a short video and want a polished Reel without manually editing in a video editor.

### What You Receive

- A clean, edited vertical Reel
- Captions timed to the spoken words
- One of three visual styles: **bold**, **cool girl**, or **cool dude**
- Background cutout effects that can place text behind the speaker
- Motion graphics, subtle sound design, and safe-zone checks for Instagram
- A 720p phone copy and a full-quality render

## Before You Start

You need a Mac, Windows 10/11 PC, or Linux computer with Claude Code, ffmpeg, Node.js 22+, and Python 3.10+ installed. The skill checks the setup on its first run and tells you how to install anything missing.

For the best result, record vertical 4K clips, keep the camera steady, and repeat lines until you have a take you like.

## Install the Skill

1. Open Claude Code.
2. Paste the following message:

```
Install this skill for me: https://github.com/Ankitanand2411/Video-edit-skill-1
```

3. Once installation finishes, run the command below.

## Main Command

```
/video-edit
```

On the first run, the skill asks for your name, Instagram handle, preferred visual style, clips folder, and projects folder. It stores these as your defaults for future edits.

## Commands and Examples

### Edit clips you have just recorded

```
/video-edit I just dropped 5 clips in my Downloads folder
```

The skill finds the newest clips, transcribes them, chooses the cleanest take for each line, and creates a finished Reel.

### Choose a different visual style for each section

```
/video-edit Use the cool girl look when I say "the cool girl aesthetic", cool dude after that, and bold everywhere else.
```

The skill changes the styling at the requested points while keeping the edit coherent.

### Edit a specific folder

```
/video-edit Edit all the clips in /Users/me/Desktop/product-launch-clips
```

Use this when your clips are not in your normal downloads folder.

### Give feedback on a completed version

```
Make the captions larger, remove the pause before "you can get", and make the background less dark.
```

The skill applies only those requested changes and re-renders a new version.

## How the Workflow Works

1. **Find and transcribe clips** — The skill reviews your clips and creates a transcript with word-level timing.
2. **Choose the best takes** — Repeated lines are compared and the cleanest complete take is selected.
3. **Build the edit** — Dead air is removed, pacing is tightened, and punch-ins are added where useful.
4. **Apply the look** — Captions, colors, typography, cutout effects, and motion graphics are added.
5. **Check the result** — The render is checked frame by frame to keep important content inside the Instagram Reel safe zone.
6. **Deliver the video** — You receive a phone-ready copy and a full-quality version, then can ask for revisions.

## Sample Input and Output

### Sample input

Five vertical phone clips of a creator explaining a product feature. The creator repeats the opening line three times, gives the main explanation in two clips, and records a call to action in the final clip.

Example request:

```
/video-edit Turn these five product-demo clips into a 25-second bold Reel. Use the strongest opening take, keep the captions large, and add a punch-in for the call to action.
```

### Expected output video

A 9:16 Reel of approximately 25 seconds with:

- The best version of the hook at the start
- Clean joins between each spoken section
- Large, accurate captions
- A punch-in during the call to action
- Bold kinetic words positioned around and behind the speaker where readable
- Audio balanced for mobile playback
- A final `.mp4` render ready to post to Instagram

## GitHub Repository

Source code, installation files, and documentation are available here:

https://github.com/Ankitanand2411/Video-edit-skill-1

## Updating the Skill

In Claude Code, paste:

```
Update the video-edit skill from https://github.com/Ankitanand2411/Video-edit-skill-1
```

Or, if you installed it manually:

```bash
git -C "$HOME/.claude/skills/video-edit" pull
```
