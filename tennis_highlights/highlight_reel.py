#!/usr/bin/env python3
"""
Tennis highlight-reel builder (pure ffmpeg, no Python dependencies).

    python3 highlight_reel.py --init        # scan ./raw_videos and write a shots.csv template
    python3 highlight_reel.py               # render ./shots.csv -> tennis_highlights.mp4
    python3 highlight_reel.py --vertical    # 1080x1920 version for Reels / TikTok / Shorts

Rows with a `speed` below 1 (e.g. 0.4) become slow-motion replays: motion-interpolated to a
smooth 60 fps with deep, pitched-down court audio and a "SLOW-MO REPLAY" label.

Pipeline
  1. Each row of shots.csv becomes one normalised segment (cached in .highlight_cache/):
       cut [start - lead_in, end + follow_through]  ->  1920x1080 (or 1080x1920) @ 60 fps
       -> lower-third shot label -> court audio cleaned + loudness-matched.
  2. Segments are joined with 0.3 s dip-to-black (or cross-dissolve) transitions,
     the optional raw_videos/music.mp3 is mixed in underneath, and the final file is encoded.

Requires ffmpeg + ffprobe on PATH (ffmpeg 4.3 or newer).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv"}
MUSIC_NAMES = ["music.mp3", "music.m4a", "music.wav", "music.aac"]
SAMPLE_RATE = 48000
CACHE_VERSION = "5"  # bump to invalidate cached segments after changing the render recipe

# Audio targets for court sound. Each clip gets a single linear gain towards TARGET_LUFS; ball
# strikes are spiky (often 25-30 dB above the room tone), so up to MAX_LIMIT_DB of those peaks may
# be shaved by a 1 ms look-ahead limiter. That's short enough to keep the racket "pop" crisp
# while the rally, footsteps and calls come up to a consistent, audible level.
TARGET_LUFS = -18.0
PEAK_CEILING_DB = -1.5
MAX_LIMIT_DB = 6.0
REPLAY_AUDIO_DB = -4.0  # slow-motion rows play pitched-down court audio, slightly quieter


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def die(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_time(value: str) -> float:
    """'74', '74.5', '01:14', '1:14.25', '00:01:14' -> seconds."""
    value = value.strip()
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", value):
        raise ValueError(f"bad timestamp {value!r} (use SS, MM:SS or HH:MM:SS, decimals allowed)")
    seconds = 0.0
    for part in value.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def fmt_time(seconds: float) -> str:
    m, s = divmod(max(seconds, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def ff_quote(value: str) -> str:
    """Quote a value for use inside an ffmpeg filtergraph option."""
    return "'" + str(value).replace("\\", "/").replace("'", r"'\''") + "'"


def run_quiet(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def run_ffmpeg(cmd: list[str], duration: float, label: str) -> None:
    """Run ffmpeg and draw a progress bar from its -progress output."""
    cmd = cmd[:1] + ["-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1"] + cmd[1:]
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    width = 28
    done = 0.0
    for line in proc.stdout:  # type: ignore[union-attr]
        key, _, val = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and val.isdigit():  # both are microseconds
            done = min(int(val) / 1e6, duration)
        elif key == "progress":
            frac = done / duration if duration > 0 else 1.0
            if val == "end":
                frac = 1.0
            elapsed = time.time() - started
            eta = (elapsed / frac - elapsed) if frac > 0.02 else 0
            bar = "#" * int(frac * width) + "-" * (width - int(frac * width))
            sys.stdout.write(f"\r  {label:<40.40} [{bar}] {frac * 100:5.1f}%  eta {eta:4.0f}s ")
            sys.stdout.flush()
    stderr = proc.stderr.read()  # type: ignore[union-attr]
    proc.wait()
    sys.stdout.write("\n")
    if proc.returncode != 0:
        die(f"ffmpeg failed ({label}):\n{stderr.strip()}\n\nCommand:\n{' '.join(cmd)}")


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            die(f"{tool} not found on PATH. Install it (macOS: `brew install ffmpeg`, "
                "Ubuntu: `sudo apt install ffmpeg`, Windows: `winget install ffmpeg`).")


def ffmpeg_has_filter(name: str) -> bool:
    out = run_quiet(["ffmpeg", "-hide_banner", "-filters"]).stdout
    return re.search(rf"^\s*\S+\s+{re.escape(name)}\s", out, re.M) is not None


def find_font() -> str | None:
    """A clean sans-serif for the lower thirds (fontfile path), or None to let ffmpeg pick."""
    if shutil.which("fc-match"):
        for pattern in ("Inter:style=SemiBold", "Inter", "Helvetica Neue:style=Medium",
                        "Arial:style=Bold", "DejaVu Sans:style=Bold", "sans-serif:style=Bold"):
            path = run_quiet(["fc-match", "-f", "%{file}", pattern]).stdout.strip()
            if path and os.path.exists(path):
                return path
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",       # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",                            # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # Linux
    ):
        if os.path.exists(path):
            return path
    return None


# --------------------------------------------------------------------------------------
# Probing & input
# --------------------------------------------------------------------------------------
@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    audio_channels: int
    hdr: bool
    codec: str


_probe_cache: dict[Path, MediaInfo] = {}


def probe(path: Path) -> MediaInfo:
    if path in _probe_cache:
        return _probe_cache[path]
    res = run_quiet(["ffprobe", "-v", "error", "-print_format", "json",
                     "-show_format", "-show_streams", str(path)])
    if res.returncode != 0:
        die(f"could not read {path}: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    vids = [s for s in data["streams"] if s.get("codec_type") == "video"
            and not s.get("disposition", {}).get("attached_pic")]
    if not vids:
        die(f"{path} has no video stream")
    v = vids[0]
    w, h = int(v["width"]), int(v["height"])
    # phone footage is often stored sideways with a rotation flag; ffmpeg auto-rotates
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(float(sd["rotation"]))
    rotation = int(float(v.get("tags", {}).get("rotate", rotation)))
    if abs(rotation) % 180 == 90:
        w, h = h, w
    num, _, den = v.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if not fps or fps > 240:
        num, _, den = v.get("r_frame_rate", "30/1").partition("/")
        fps = float(num) / float(den or 1)
    info = MediaInfo(
        path=path,
        duration=float(data["format"].get("duration") or v.get("duration") or 0),
        width=w, height=h, fps=fps,
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
        audio_channels=next((int(s.get("channels", 2)) for s in data["streams"]
                             if s.get("codec_type") == "audio"), 0),
        hdr=v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
        codec=v.get("codec_name", "?"),
    )
    _probe_cache[path] = info
    return info


def list_videos(videos_dir: Path) -> list[Path]:
    if not videos_dir.is_dir():
        return []
    return sorted(p for p in videos_dir.iterdir()
                  if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith("."))


def resolve_video(name: str, videos_dir: Path) -> Path:
    name = name.strip()
    direct = videos_dir / name
    if direct.is_file():
        return direct
    for p in list_videos(videos_dir):  # case-insensitive, extension optional
        if p.name.lower() == name.lower() or p.stem.lower() == name.lower():
            return p
    die(f"video {name!r} not found in {videos_dir}/ (available: "
        f"{', '.join(p.name for p in list_videos(videos_dir)) or 'none'})")
    raise AssertionError


@dataclass
class Shot:
    row: int
    video: Path
    start: float
    end: float
    label: str
    focus: float = 0.5           # horizontal crop centre 0..1 (used when cropping)
    speed: float = 1.0           # playback speed; < 1 = slow-motion replay
    clip_start: float = 0.0      # after lead-in / follow-through / clamping
    clip_end: float = 0.0
    frames: int = 0
    segment: Path | None = None
    gain_db: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Length of the source cut (seconds of footage)."""
        return self.clip_end - self.clip_start

    @property
    def out_duration(self) -> float:
        """Length on screen, after any slow motion."""
        return self.duration / self.speed

    @property
    def is_replay(self) -> bool:
        return self.speed < 0.999


def load_shots(csv_path: Path, videos_dir: Path) -> list[Shot]:
    if not csv_path.is_file():
        die(f"{csv_path} not found. Run `python3 {Path(sys.argv[0]).name} --init` to create a template.")
    shots: list[Shot] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    for i, row in enumerate(csv.reader(lines, skipinitialspace=True), start=1):
        row = [c.strip() for c in row]
        if not row or not any(row):
            continue
        if row[0].lower() in ("filename", "file", "video"):
            continue  # header
        if len(row) < 4:
            die(f"{csv_path} row {i}: expected `filename, start_time, end_time, shot_label[, focus[, speed]]`, got {row}")
        try:
            start, end = parse_time(row[1]), parse_time(row[2])
        except ValueError as exc:
            die(f"{csv_path} row {i}: {exc}")
        if end <= start:
            die(f"{csv_path} row {i}: end_time {row[2]} is not after start_time {row[1]}")
        focus = 0.5
        if len(row) >= 5 and row[4]:
            try:
                focus = min(max(float(row[4]), 0.0), 1.0)
            except ValueError:
                die(f"{csv_path} row {i}: focus must be a number between 0 and 1, got {row[4]!r}")
        speed = 1.0
        if len(row) >= 6 and row[5]:
            try:
                speed = float(row[5].rstrip("xX"))
            except ValueError:
                speed = 0.0
            if not 0.1 <= speed <= 1.0:
                die(f"{csv_path} row {i}: speed must be between 0.1 and 1 (e.g. 0.4 for slow-mo), got {row[5]!r}")
        shots.append(Shot(row=i, video=resolve_video(row[0], videos_dir), start=start, end=end,
                          label=row[3], focus=focus, speed=speed))
    if not shots:
        die(f"{csv_path} has no shots yet. Add rows like:  match1.mp4, 01:14, 01:21, Forehand Winner")
    return shots


# --------------------------------------------------------------------------------------
# Filter builders
# --------------------------------------------------------------------------------------
def fit_filter(info: MediaInfo, W: int, H: int, mode: str, focus: float) -> str:
    """Video chain that maps the source frame onto a WxH canvas. Input/Output: one stream."""
    src_ar, dst_ar = info.width / info.height, W / H
    if abs(src_ar - dst_ar) / dst_ar < 0.01:
        return f"scale={W}:{H}:flags=lanczos"
    if mode == "crop":
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:{H}:x=(iw-{W})*{focus:.3f}:y=(ih-{H})/2")
    if mode == "pad":
        return (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    # blur: the same footage, zoomed + blurred + dimmed, fills the empty sides
    bw, bh = W // 4 // 2 * 2, H // 4 // 2 * 2
    return (f"split=2[fg_in][bg_in];"
            f"[bg_in]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
            f"boxblur=12:3,eq=brightness=-0.10:saturation=0.75,scale={W}:{H}[bg];"
            f"[fg_in]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2")


def lower_third_filter(label_file: Path, kicker: str, font: str | None, W: int, H: int,
                       fps: float, start: float, hold: float) -> str:
    """Transparent lower-third graphic (accent bar + dark plate + label) with alpha fades.
    Output label: [lt]. Positioned for the given canvas; shown from `start` for `hold` seconds."""
    vertical = H > W
    size = round(min(W, H) * (0.040 if not vertical else 0.046))
    pad = round(size * 0.48)
    accent = max(6, round(size * 0.16))
    x = round(W * (0.055 if not vertical else 0.075))
    y = round(H * (0.80 if not vertical else 0.72))  # top of the label text
    kick_size = round(size * 0.48)
    fontopt = f"fontfile={ff_quote(font)}:" if font else ""
    fade = 0.25
    common = f"{fontopt}textfile={ff_quote(label_file)}:expansion=none:fontsize={size}:x={x + accent}:y={y}"
    return (
        f"color=c=black@0.0:s={W}x{H}:r={fps:g}:d={hold:.3f},format=rgba,"
        # 1) accent: same text box, drawn in tennis-ball yellow and shifted left by `accent` px
        f"drawtext={fontopt}textfile={ff_quote(label_file)}:expansion=none:fontsize={size}:"
        f"x={x}:y={y}:fontcolor=black@0.0:box=1:boxcolor=0xD7F23A@1.0:boxborderw={pad},"
        # 2) dark plate + white label on top
        f"drawtext={common}:fontcolor=white:box=1:boxcolor=0x0E1116@1.0:boxborderw={pad},"
        # 3) small kicker above the plate
        f"drawtext={fontopt}text={ff_quote(kicker)}:expansion=none:fontsize={kick_size}:"
        f"fontcolor=0xD7F23A:x={x}:y={y - pad - kick_size - round(kick_size * 0.7)}:"
        f"shadowcolor=black@0.6:shadowx=1:shadowy=1,"
        # overall opacity: the plate is drawn opaque so the yellow accent can't bleed through it
        f"colorchannelmixer=aa=0.86,"
        f"fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={hold - fade:.3f}:d={fade}:alpha=1,"
        f"setpts=PTS+{start:.3f}/TB[lt]"
    )


HDR_TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
               "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


# --------------------------------------------------------------------------------------
# Stage 1: per-shot segments
# --------------------------------------------------------------------------------------
def measure_audio(shot: Shot) -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of the shot's court audio."""
    res = run_quiet(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{shot.clip_start:.3f}",
                     "-t", f"{shot.duration:.3f}", "-i", str(shot.video), "-vn",
                     "-af", "highpass=f=60,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                     "-f", "null", "-"])
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not match:
        return (TARGET_LUFS, PEAK_CEILING_DB)
    data = json.loads(match.group(0))
    try:
        return float(data["input_i"]), float(data["input_tp"])
    except (ValueError, KeyError):  # silence -> "-inf"
        return (TARGET_LUFS, PEAK_CEILING_DB)


def render_segment(shot: Shot, idx: int, total: int, kicker: str, args, W: int, H: int,
                   fps: float, font: str | None, cache: Path, can_tonemap: bool) -> None:
    info = probe(shot.video)
    key_src = json.dumps([CACHE_VERSION, str(shot.video.resolve()), shot.video.stat().st_mtime,
                          shot.clip_start, shot.clip_end, shot.label, shot.focus, W, H, fps,
                          args.fit, args.labels, font, idx, kicker, args.label_seconds,
                          shot.speed, args.fast_slowmo if shot.is_replay else None])
    key = hashlib.sha1(key_src.encode()).hexdigest()[:12]
    shot.segment = cache / f"seg_{idx:03d}_{key}.mkv"
    shot.frames = max(1, round(shot.out_duration * fps))
    name = f"[{idx}/{total}] {shot.label}"
    if shot.segment.exists() and shot.segment.stat().st_size > 0:
        print(f"  {name:<40.40} (cached)")
        return

    lufs, peak = measure_audio(shot) if info.has_audio else (TARGET_LUFS, PEAK_CEILING_DB)
    shot.gain_db = min(TARGET_LUFS - lufs, PEAK_CEILING_DB - peak + MAX_LIMIT_DB, 24.0)

    vchain = []
    if info.hdr:
        if can_tonemap:
            vchain.append(HDR_TONEMAP)
        else:
            print("  (warning: HDR source but this ffmpeg lacks zscale; colours may look flat)")
    if shot.is_replay:
        vchain.append(f"setpts=(PTS-STARTPTS)/{shot.speed:.4f}")
        if args.fast_slowmo:  # cheap: blend neighbouring frames
            vchain.append(f"framerate=fps={fps:g}")
        else:  # motion-compensated in-between frames: smooth, but CPU-heavy
            vchain.append(f"minterpolate=fps={fps:g}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
    else:
        vchain.append(f"fps={fps:g}")
    vchain.append(fit_filter(info, W, H, args.fit, shot.focus))
    vchain.append("setsar=1,format=yuv420p")
    # clone the last frame if the source runs out early, then cut to an exact frame count
    vchain.append(f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={shot.frames},setpts=PTS-STARTPTS")
    graph = [f"[0:v]{','.join(vchain)}[base]"]

    if args.labels and shot.label:
        label_file = cache / f"label_{idx:03d}.txt"
        label_file.write_text(shot.label, encoding="utf-8")
        hold = min(args.label_seconds, max(shot.out_duration - args.transition - 0.4, 0.5))
        lt_start = args.transition + 0.05  # appear once the incoming transition has settled
        graph.append(lower_third_filter(label_file, kicker, font, W, H, fps,
                                        lt_start, hold))
        graph.append("[base][lt]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]")
    else:
        graph.append("[base]null[v]")

    samples = round(shot.frames / fps * SAMPLE_RATE)
    ceiling = 10 ** (PEAK_CEILING_DB / 20)
    # pan duplicates mono phone audio to both sides at full level (a plain upmix costs 3 dB)
    upmix = "pan=stereo|c0=c0|c1=c0," if info.audio_channels == 1 else ""
    gain = shot.gain_db
    slow = ""
    if shot.is_replay:  # classic slow-mo sound: stretched and pitched down together
        slow = f"asetrate={round(SAMPLE_RATE * shot.speed)},aresample={SAMPLE_RATE},"
        gain += REPLAY_AUDIO_DB
    achain = (f"aresample={SAMPLE_RATE},{slow}{upmix}aformat=sample_fmts=fltp:channel_layouts=stereo,"
              f"highpass=f={40 if shot.is_replay else 60},volume={gain:.2f}dB,"
              f"alimiter=limit={ceiling:.3f}:attack=1:release=40:level=disabled,"
              f"apad,atrim=end_sample={samples},asetpts=PTS-STARTPTS[a]")
    cmd = ["ffmpeg", "-y", "-ss", f"{shot.clip_start:.3f}", "-t", f"{shot.duration + 0.5:.3f}",
           "-i", str(shot.video)]
    if info.has_audio:
        graph.append(f"[0:a]{achain}")
    else:
        cmd += ["-f", "lavfi", "-t", f"{shot.duration + 0.5:.3f}",
                "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo"]
        graph.append(f"[1:a]{achain}")

    tmp = shot.segment.with_suffix(".part.mkv")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
            "-g", str(round(fps)), "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), str(tmp)]
    run_ffmpeg(cmd, shot.frames / fps, name)
    tmp.replace(shot.segment)


# --------------------------------------------------------------------------------------
# Stage 2: join with transitions + music
# --------------------------------------------------------------------------------------
def assemble(shots: list[Shot], args, W: int, H: int, fps: float, music: Path | None,
             output: Path) -> float:
    T = args.transition
    n = len(shots)
    durs = [s.frames / fps for s in shots]
    min_d = min(durs)
    if n > 1 and T >= min_d / 2:
        T = round(min_d / 2 - 0.05, 2)
        print(f"  (transition shortened to {T}s because a shot is only {min_d:.2f}s long)")
    total = sum(durs) - T * (n - 1)

    cmd = ["ffmpeg", "-y"]
    for s in shots:
        cmd += ["-i", str(s.segment)]
    graph = []
    for i in range(n):
        graph.append(f"[{i}:v]settb=AVTB,fps={fps:g},format=yuv420p[v{i}]")
        graph.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=stereo[a{i}]")

    xfade = "fadeblack" if args.transition_style == "dip" else "fade"
    v_prev, a_prev, offset = "v0", "a0", 0.0
    for i in range(1, n):
        offset += durs[i - 1] - T
        graph.append(f"[{v_prev}][v{i}]xfade=transition={xfade}:duration={T:.3f}:offset={offset:.4f}[vx{i}]")
        graph.append(f"[{a_prev}][a{i}]acrossfade=d={T:.3f}:c1=tri:c2=tri[ax{i}]")
        v_prev, a_prev = f"vx{i}", f"ax{i}"

    fade_in, fade_out = 0.25, 0.6
    graph.append(f"[{v_prev}]fade=t=in:st=0:d={fade_in},"
                 f"fade=t=out:st={total - fade_out:.3f}:d={fade_out},format=yuv420p[vout]")
    court = f"[{a_prev}]afade=t=in:st=0:d=0.05,afade=t=out:st={total - fade_out:.3f}:d={fade_out}"
    if music:
        m = n  # input index of the music
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        graph.append(f"{court}[court]")
        graph.append(f"[{m}:a]aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"atrim=duration={total:.3f},asetpts=PTS-STARTPTS,volume={args.music_volume:.3f},"
                     f"afade=t=in:st=0:d=1.0,afade=t=out:st={max(total - 2.5, 0):.3f}:d=2.5[mus]")
        # sum (not average) so court audio stays at 100%; a limiter catches any overs
        graph.append("[court][mus]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3,"
                     "alimiter=limit=0.94:attack=2:release=50:level=disabled[aout]")
    else:
        graph.append(f"{court},alimiter=limit=0.94:attack=2:release=50:level=disabled[aout]")

    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", f"{fps:g}", "-g", str(round(fps)),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "256k", "-ar", str(SAMPLE_RATE),
            "-movflags", "+faststart", "-t", f"{total:.3f}", str(output)]
    run_ffmpeg(cmd, total, f"Final encode -> {output.name}")
    return total


# --------------------------------------------------------------------------------------
# --init: write a template
# --------------------------------------------------------------------------------------
TEMPLATE_HEADER = """\
# Tennis highlight reel - shot list
# ---------------------------------------------------------------------------------
# One row per shot, in the order they should appear in the reel:
#
#   filename, start_time, end_time, shot_label[, focus[, speed]]
#
#   filename    file inside ./raw_videos/ (case-insensitive; extension optional)
#   start_time  just before the shot starts (split step / unit turn)
#   end_time    the moment the ball BOUNCES on the other side
#               (the script adds a 0.2 s lead-in and 0.5 s follow-through for you)
#   shot_label  text for the lower-third, e.g. Forehand Winner, Ace, Backhand Down-the-Line
#               (wrap it in "double quotes" if it contains a comma)
#   focus       optional 0.0-1.0 horizontal crop centre, only used when cropping
#               (e.g. --vertical): 0 = keep the left edge, 0.5 = centre, 1 = right edge
#   speed       optional playback speed, 1 = real time (default). Use 0.4 for a smooth
#               slow-motion replay: repeat a great shot on the next row with a tight window
#               around contact (about 1 s before to 0.8 s after) and speed 0.4
#
# Timestamps: SS, SS.ss, MM:SS, MM:SS.ss or HH:MM:SS. Lines starting with # are ignored.
# Aim for 4-7 s per shot (including the padding) to keep the reel punchy.
# ---------------------------------------------------------------------------------
filename, start_time, end_time, shot_label, focus, speed
"""


def write_template(csv_path: Path, videos_dir: Path) -> None:
    if csv_path.exists():
        die(f"{csv_path} already exists - not overwriting it. Delete it first to regenerate the template.")
    videos = list_videos(videos_dir)
    lines = [TEMPLATE_HEADER, "\n# Videos found in raw_videos/ (uncomment a line and fill in times):\n"]
    for p in videos:
        info = probe(p)
        lines.append(f"#   {p.name}  ({fmt_time(info.duration)}, {info.width}x{info.height} @ {info.fps:g} fps)\n")
        lines.append(f"# {p.name}, 00:00.0, 00:05.0, Forehand Winner\n")
    if not videos:
        lines.append("#   (none yet - drop your .mp4 / .mov files into raw_videos/)\n")
        lines.append("# match1.mp4, 01:14, 01:21, Inside-Out Forehand Winner\n")
    csv_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote template {csv_path} listing {len(videos)} video(s). Fill it in and run again.")


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Build a tennis highlight reel from a shot list.",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--videos", default="raw_videos", help="folder with the raw clips (+ optional music.mp3)")
    ap.add_argument("--shots", default="shots.csv", help="shot list CSV")
    ap.add_argument("-o", "--output", default=None,
                    help="output file (default: tennis_highlights.mp4, or tennis_highlights_vertical.mp4 with --vertical)")
    ap.add_argument("--init", action="store_true", help="write a shots.csv template and exit")
    ap.add_argument("--dry-run", action="store_true", help="validate the shot list and print the plan only")
    ap.add_argument("--vertical", action="store_true", help="9:16 1080x1920 output for Reels/TikTok/Shorts")
    ap.add_argument("--fit", choices=["auto", "blur", "crop", "pad"], default="auto",
                    help="how to fit sources whose aspect ratio differs from the output "
                         "(auto = blur for 16:9, crop for vertical)")
    ap.add_argument("--fps", default="60", help="output frame rate, or 'native' to match the sources")
    ap.add_argument("--lead-in", type=float, default=0.2, help="seconds added before start_time")
    ap.add_argument("--follow-through", type=float, default=0.5, help="seconds added after end_time (the bounce)")
    ap.add_argument("--transition", type=float, default=0.3, help="transition length in seconds")
    ap.add_argument("--transition-style", choices=["dip", "dissolve"], default="dip",
                    help="dip = dip-to-black, dissolve = cross-dissolve")
    ap.add_argument("--fast-slowmo", action="store_true",
                    help="blend frames for slow-motion rows instead of motion interpolation "
                         "(much faster to render, slightly ghosty)")
    ap.add_argument("--no-labels", dest="labels", action="store_false", help="disable lower-third labels")
    ap.add_argument("--label-seconds", type=float, default=1.5, help="how long each label stays on screen")
    ap.add_argument("--music", default=None, help="background track (default: raw_videos/music.mp3 if present)")
    ap.add_argument("--music-volume", type=float, default=0.25, help="music level relative to court audio (0.2-0.3)")
    ap.add_argument("--crf", type=int, default=18, help="x264 quality for the final file (lower = better/larger)")
    ap.add_argument("--preset", default="medium", help="x264 preset for the final file")
    ap.add_argument("--clean", action="store_true", help="delete cached segments before rendering")
    args = ap.parse_args()

    check_tools()
    videos_dir = Path(args.videos)
    csv_path = Path(args.shots)
    if args.init:
        write_template(csv_path, videos_dir)
        return

    W, H = (1080, 1920) if args.vertical else (1920, 1080)
    if args.fit == "auto":
        args.fit = "crop" if args.vertical else "blur"
    output = Path(args.output or ("tennis_highlights_vertical.mp4" if args.vertical else "tennis_highlights.mp4"))

    shots = load_shots(csv_path, videos_dir)
    if args.fps == "native":
        fps = max(round(probe(s.video).fps, 3) for s in shots)
    else:
        try:
            fps = float(args.fps)
        except ValueError:
            die("--fps must be a number or 'native'")

    music: Path | None = None
    if args.music:
        music = Path(args.music)
        if not music.is_file():
            die(f"music file {music} not found")
    else:
        music = next((videos_dir / m for m in MUSIC_NAMES if (videos_dir / m).is_file()), None)

    # ---- plan
    print(f"\nShot list: {csv_path}  ({len(shots)} shots)   Output: {output}  {W}x{H} @ {fps:g} fps")
    print(f"Fit: {args.fit}   Transition: {args.transition}s {args.transition_style}   "
          f"Labels: {'on' if args.labels else 'off'}   "
          f"Music: {f'{music.name} @ {args.music_volume:.0%}' if music else 'none (add raw_videos/music.mp3)'}\n")
    print(f"  {'#':>2}  {'video':<32} {'cut (with padding)':<22} {'len':>5} {'speed':>5}  label")
    for i, s in enumerate(shots, 1):
        info = probe(s.video)
        s.clip_start = max(0.0, s.start - args.lead_in)
        s.clip_end = min(info.duration - 1 / max(info.fps, 1), s.end + args.follow_through)
        if s.clip_end - s.clip_start < 0.5:
            die(f"shot {i} ({s.label}) is shorter than 0.5 s after clamping to the video length "
                f"({fmt_time(info.duration)}) - check its timestamps")
        warn = ""
        if s.start >= info.duration:
            die(f"shot {i} ({s.label}) starts at {fmt_time(s.start)} but {s.video.name} is only "
                f"{fmt_time(info.duration)} long")
        if s.out_duration > 8:
            warn = "  <- long; consider trimming for pace"
        elif s.out_duration < 3:
            warn = "  <- short"
        print(f"  {i:>2}  {s.video.name:<32.32} {fmt_time(s.clip_start)}-{fmt_time(s.clip_end)}    "
              f"{s.out_duration:4.1f}s {s.speed:4.2g}x  {s.label}{warn}")
    est = sum(s.out_duration for s in shots) - args.transition * (len(shots) - 1)
    n_live = sum(not s.is_replay for s in shots)
    print(f"\n  Estimated reel length: {est:.1f}s  ({n_live} shots, {len(shots) - n_live} slow-mo replays)")
    if args.dry_run:
        return

    cache = Path(".highlight_cache")
    if args.clean and cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(exist_ok=True)
    font = find_font() if args.labels else None
    can_tonemap = any(probe(s.video).hdr for s in shots) and ffmpeg_has_filter("zscale")

    t0 = time.time()
    print(f"\nStage 1/2 - cutting & normalising shots{f' (font: {Path(font).name})' if font else ''}")
    if any(s.is_replay for s in shots) and not args.fast_slowmo:
        print("  (slow-mo replays use motion interpolation - expect ~1-2 min each the first time; "
              "they're cached afterwards. --fast-slowmo renders them quickly)")
    shot_no = 0
    for i, s in enumerate(shots, 1):
        if s.is_replay:
            kicker = f"SLOW-MO REPLAY  ·  {s.speed:g}×"
        else:
            shot_no += 1
            kicker = f"SHOT {shot_no} / {n_live}"
        render_segment(s, i, len(shots), kicker, args, W, H, fps, font, cache, can_tonemap)

    print("\nStage 2/2 - transitions, audio mix & final encode")
    total = assemble(shots, args, W, H, fps, music, output)

    # tidy cache: keep only segments used by this run (so edits re-render only what changed)
    used = {s.segment.name for s in shots if s.segment}
    for p in cache.glob("seg_*.mkv"):
        if p.name not in used:
            p.unlink()

    size_mb = output.stat().st_size / 1e6
    print(f"\nDone in {time.time() - t0:.0f}s -> {output}  ({total:.1f}s, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
