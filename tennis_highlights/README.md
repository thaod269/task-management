# Tennis highlight reel

Turns a list of shot timestamps into a fast, consistent highlight reel using only **ffmpeg**. You don't need to install any Python packages.

```
tennis_highlights/
├── highlight_reel.py      # the renderer
├── shots.csv              # your shot list (edit this)
├── raw_videos/            # drop .mp4 / .mov clips here (+ optional music.mp3)
├── .highlight_cache/      # per-shot render cache (auto, safe to delete)
└── tennis_highlights.mp4  # output
```

## Quick start

```bash
cd tennis_highlights
python3 highlight_reel.py --init      # only if shots.csv doesn't exist: writes a template listing your videos
python3 highlight_reel.py --dry-run   # check the cut points and the reel length
python3 highlight_reel.py             # render tennis_highlights.mp4
python3 highlight_reel.py --vertical  # render tennis_highlights_vertical.mp4 (1080x1920)
```

## shots.csv

```
filename, start_time, end_time, shot_label[, focus[, speed]]
match1.mp4, 01:14, 01:21, Inside-Out Forehand Winner
match1.mp4, 01:16.2, 01:18.1, Inside-Out Forehand Winner, , 0.4
match1.mp4, 03:02.5, 03:07, "Ace, T serve"
```

* `end_time` is the moment the ball **bounces on the other side**. The script adds 0.2 s before `start_time` and 0.5 s after `end_time` for you.
* Timestamps can be written as `SS`, `SS.ss`, `MM:SS`, `MM:SS.ss` or `HH:MM:SS`.
* `focus` is optional. It sets the horizontal crop centre from 0 to 1 and only applies when cropping, for example with `--vertical`.
* `speed` is optional and defaults to 1 (real time). Set it to `0.4` to turn a row into a **slow-motion replay**. Repeat a great shot on the next row with a tight window, roughly 1 s before contact to 0.8 s after. Replays are motion-interpolated to a smooth 60 fps and use deep, pitched-down court audio. Their label kicker reads "SLOW-MO REPLAY". Interpolation is CPU-heavy, about 1–2 minutes per replay on the first render, and the result is cached afterwards. `--fast-slowmo` blends frames instead, which renders in seconds.
* Rows are rendered in the order they appear in the file. Lines starting with `#` are ignored.

## What it does

| Step | Detail |
|---|---|
| Cut | Frame-accurate cut of `[start − 0.2 s, end + 0.5 s]`, clamped to the clip length |
| Normalise | 1920×1080 at 60 fps (`--fps native` keeps the source rate). Clips with a different aspect ratio get a blurred fill of the same footage (`--fit blur`). You can use `crop` or `pad` instead. With `--vertical`, the output is 1080×1920 and crops by default. HDR iPhone footage is tone-mapped to SDR. |
| Label | Off by default, so the footage stays clean. With `--labels`, each shot gets a lower-third with a "SHOT n / N" kicker above the shot label. It fades in once the transition has finished and stays for 1.5 s (`--label-seconds`). |
| Court audio | A 60 Hz high-pass removes rumble. Each clip then gets one linear gain towards −18 LUFS, and a 1 ms limiter trims at most 6 dB off the strike peaks. Racket pops stay crisp and every clip plays at a similar level. |
| Transitions | 0.3 s dip-to-black (`--transition-style dissolve` gives a cross-dissolve) plus a matching audio crossfade |
| Music | If `raw_videos/music.mp3` exists (or you pass `--music path`), it is looped or trimmed to the reel's length, faded, and mixed in at 25 % (`--music-volume 0.2`–`0.3`). Court audio stays at 100 %. |
| Encode | H.264 High at CRF 18, AAC 256k, `+faststart`, ready for phones and social media |

Rendered shots are cached by their settings. If you edit one row, only that shot is re-rendered. Use `--clean` to force a full re-render.

Run `python3 highlight_reel.py --help` to see every option.
