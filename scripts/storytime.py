#!/usr/bin/env python3
"""Storytime short: script text → AI voice-over (ElevenLabs) → 9:16 video with
one-word captions, cutting to a new gameplay clip at every sentence.

Usage:
  storytime.py story.txt --out work/story1 [--clips ~/Movies/gta] [--voice ID]
               [--game-volume 0.15] [--caption-color white]

- story.txt : the voice-over text (one story, ~60-180 words).
- --clips   : folder of YOUR OWN gameplay recordings (.mp4/.mov). Without it, a
              placeholder background is used so you can preview the timing.
- Needs ELEVENLABS_API_KEY in the environment (unless a proxy injects it).
Writes <out>/voice.mp3, <out>/words.json and <out>/story.mp4.
"""
import argparse
import base64
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import urllib.request

W, H = 1080, 1920
DEFAULT_VOICE = "3Tp5mYhT9wrfnry9pzvV"  # "Hugo – Punchy French Creator"
COLORS = {"white": "&H00FFFFFF", "yellow": "&H0000F0FF", "green": "&H0040FF40",
          "cyan": "&H00FFFF00", "orange": "&H00008CFF"}


def tts(text, voice, out_dir):
    key = os.environ.get("ELEVENLABS_API_KEY", "set-by-proxy")
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
                       "voice_settings": {"stability": 0.4, "similarity_boost": 0.8,
                                          "style": 0.35, "use_speaker_boost": True}}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    mp3 = os.path.join(out_dir, "voice.mp3")
    open(mp3, "wb").write(base64.b64decode(d["audio_base64"]))
    al = d["alignment"]
    words, cur, cs = [], "", None
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"],
                        al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": cs, "e": last_e})
            cur, cs = "", None
            continue
        if cs is None:
            cs = s
        cur += ch
        last_e = e
    if cur:
        words.append({"w": cur, "s": cs, "e": last_e})
    json.dump(words, open(os.path.join(out_dir, "words.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    return mp3, words


def duration(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def has_audio(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    return bool(out.strip())


def sentence_starts(words):
    starts = [0.0]
    for i, w in enumerate(words[:-1]):
        if re.search(r"[.!?…:]$", w["w"]) or re.search(r"[.!?…]\W*$", w["w"]):
            starts.append(words[i + 1]["s"])
    return starts


def ass_time(t):
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def build_ass(path, words, total, color, font, placeholder):
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
             "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
             "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Word,{font},110,{color},&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,8,4,5,60,60,0,1",
             f"Style: Ph,{font},54,&H60FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,60,60,300,1",
             "", "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    if placeholder:
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total)},Ph,,0,0,0,,"
                     "(ton gameplay GTA ici)")
    for i, w in enumerate(words):
        end = words[i + 1]["s"] if i + 1 < len(words) else w["e"] + 0.4
        end = max(end, w["s"] + 0.12)
        if not re.search(r"\w", w["w"]):
            continue  # lone punctuation like ":" or "…"
        txt = w["w"].strip(",.;:…«»\"").replace("{", "(").replace("}", ")").replace("\\", "")
        lines.append(f"Dialogue: 1,{ass_time(w['s'])},{ass_time(end)},Word,,0,0,0,,"
                     f"{{\\fscx80\\fscy80\\t(0,80,\\fscx100\\fscy100)}}{txt}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--out", required=True)
    ap.add_argument("--clips", help="folder with your own gameplay recordings")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--game-volume", type=float, default=0.15)
    ap.add_argument("--caption-color", default="white")
    ap.add_argument("--font", default="Arial Black")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)
    os.makedirs(a.out, exist_ok=True)
    text = open(a.story, encoding="utf-8").read().strip()

    mp3 = os.path.join(a.out, "voice.mp3")
    wj = os.path.join(a.out, "words.json")
    if os.path.exists(mp3) and os.path.exists(wj):
        print("✓ Voix off déjà générée")
        words = json.load(open(wj, encoding="utf-8"))
    else:
        print("🎙️ Génération de la voix off…")
        try:
            mp3, words = tts(text, a.voice, a.out)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"✗ ElevenLabs a échoué ({e}). Vérifie ELEVENLABS_API_KEY.")
    total = duration(mp3) + 0.6
    print(f"✓ Voix off : {total:.1f}s, {len(words)} mots")

    clips = []
    if a.clips:
        for ext in ("mp4", "mov", "m4v", "mkv", "MP4", "MOV"):
            clips += glob.glob(os.path.join(os.path.expanduser(a.clips), f"*.{ext}"))
        clips = [c for c in sorted(clips) if duration(c) > 1]
        random.shuffle(clips)
        if not clips:
            sys.exit(f"✗ Aucune vidéo trouvée dans {a.clips}")
    starts = sentence_starts(words) + [total]

    tmp = tempfile.mkdtemp()
    parts = []
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          "setsar=1,fps=30,format=yuv420p")
    for i in range(len(starts) - 1):
        d = max(0.3, starts[i + 1] - starts[i])
        part = os.path.join(tmp, f"p{i:03d}.mp4")
        if clips:
            c = clips[i % len(clips)]
            cd = duration(c)
            off = random.uniform(0, max(0.0, cd - d - 0.1)) if cd > d else 0
            loop = ["-stream_loop", "-1"] if cd < d else []
            ain = ["-map", "0:a"] if has_audio(c) else ["-map", "1:a"]
            cmd = ["ffmpeg", "-v", "error", "-y", *loop, "-ss", f"{off:.2f}", "-i", c,
                   "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                   "-t", f"{d:.3f}", "-map", "0:v", *ain, "-vf", vf,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-c:a", "aac", "-ar", "48000", "-ac", "2", part]
        else:
            hue = (i * 47) % 360
            cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                   "-i", f"gradients=s={W}x{H}:c0=0x1d2b64:c1=0xf8cdda:speed=0.02:d={d:.3f},"
                         f"hue=h={hue}",
                   "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{d:.3f}",
                   "-vf", "format=yuv420p,fps=30", "-c:v", "libx264", "-preset", "veryfast",
                   "-c:a", "aac", "-ar", "48000", "-ac", "2", part]
        subprocess.run(cmd, check=True)
        parts.append(part)
        print(f"  ● plan {i + 1}/{len(starts) - 1} ({d:.1f}s)", flush=True)

    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    joined = os.path.join(tmp, "joined.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", joined], check=True)

    ass = os.path.join(a.out, "captions.ass")
    build_ass(ass, words, total, COLORS.get(a.caption_color, a.caption_color), a.font,
              placeholder=not clips)
    out = os.path.join(a.out, "story.mp4")
    fc = (f"[0:v]ass=captions.ass[v];"
          f"[0:a]volume={a.game_volume}[g];[1:a]volume=1.0[vo];"
          f"[g][vo]amix=inputs=2:duration=longest:normalize=0,"
          f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.abspath(joined),
                    "-i", os.path.abspath(mp3), "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "story.mp4"],
                   check=True, cwd=a.out)
    print(f"✓ Vidéo prête → {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
