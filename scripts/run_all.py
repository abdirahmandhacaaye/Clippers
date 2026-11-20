#!/usr/bin/env python3
"""One command: stream link (or local video file) → finished shorts.

Usage:
  python3.12 scripts/run_all.py "https://www.youtube.com/watch?v=..."
  python3.12 scripts/run_all.py "<link>" --count 5 --model base --layout crop
  python3.12 scripts/run_all.py work/<id>          # resume an earlier run

Steps already done (files present) are skipped, so you can re-run after an
interruption. Shorts end up in work/<id>/shorts/ and the folder is opened.
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def step(title):
    print(f"\n━━━ {title} ━━━", flush=True)


def run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"\n✗ Étape échouée : {script}. Envoie une photo de l'erreur ci-dessus.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="stream/video link, a local video file, or an existing work/<id> folder")
    ap.add_argument("--count", default="0", help="number of shorts (default: based on length)")
    ap.add_argument("--model", default="small", help="whisper model: base (faster) | small | medium (better)")
    ap.add_argument("--language", help="e.g. fr, en, hi (auto if omitted)")
    ap.add_argument("--layout", default="blur", choices=["blur", "crop", "facecam"])
    ap.add_argument("--facecam", help="x,y,w,h fractions, for --layout facecam")
    ap.add_argument("--section", help="only part of the stream, e.g. 01:00:00-02:00:00")
    ap.add_argument("--caption-color", default="yellow")
    ap.add_argument("--cookies-from-browser", help="e.g. chrome, if the site asks you to sign in")
    a = ap.parse_args()

    src = a.source
    if os.path.isdir(src) and os.path.exists(os.path.join(src, "source.mp4")):
        wd = src
    else:
        if os.path.isfile(src):
            name = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(src))[0])[:40]
        else:
            m = re.search(r"(?:v=|youtu\.be/|live/|videos/|shorts/)([A-Za-z0-9_-]{6,})", src)
            name = m.group(1) if m else time.strftime("stream-%Y%m%d-%H%M")
        wd = os.path.join(ROOT, "work", name)
        os.makedirs(wd, exist_ok=True)

    t0 = time.time()
    source = os.path.join(wd, "source.mp4")
    if not os.path.exists(source):
        if os.path.isfile(src):
            step("1/5 Copie de la vidéo")
            shutil.copy(src, source)
        else:
            step("1/5 Téléchargement du stream")
            args = [src, "--out", wd]
            if a.section:
                args += ["--section", a.section]
            if a.cookies_from_browser:
                args += ["--cookies-from-browser", a.cookies_from_browser]
            run("download.py", *args)
    else:
        print("✓ 1/5 Vidéo déjà téléchargée")

    if not os.path.exists(os.path.join(wd, "transcript.json")):
        step(f"2/5 Transcription (modèle '{a.model}', c'est l'étape la plus longue)")
        args = [source, "--model", a.model]
        if a.language:
            args += ["--language", a.language]
        run("transcribe.py", *args)
    else:
        print("✓ 2/5 Transcription déjà faite")

    step("3/5 Recherche des meilleurs moments")
    run("find_hype.py", wd)

    clips = os.path.join(wd, "clips.json")
    if not os.path.exists(clips):
        step("4/5 Choix des clips")
        run("auto_clips.py", wd, "--count", a.count)
    else:
        print("✓ 4/5 clips.json existe déjà (supprime-le pour re-choisir)")

    step("5/5 Montage des shorts")
    args = [wd, "--layout", a.layout, "--caption-color", a.caption_color]
    if a.facecam:
        args += ["--facecam", a.facecam]
    run("make_shorts.py", *args)
    run("make_shorts.py", wd, "--preview")

    out = os.path.abspath(os.path.join(wd, "shorts"))
    mins = (time.time() - t0) / 60
    print(f"\n🎉 Terminé en {mins:.0f} min ! Tes shorts sont ici :\n   {out}")
    if platform.system() == "Darwin":
        subprocess.run(["open", out])


if __name__ == "__main__":
    main()
