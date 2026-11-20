#!/usr/bin/env python3
"""Pick clips automatically from hype.json + transcript.json (no AI needed).

Usage: auto_clips.py work/<id> [--count N] [--min 20] [--max 50]
Writes clips.json, ready for make_shorts.py. Clips start and end on sentence
boundaries around the loudest/most hyped moments and never overlap.
"""
import argparse
import json
import os
import re


def pick_bounds(segs, words, peak, lo, hi, duration):
    """Start a few seconds before the peak on a sentence start; end on a sentence end."""
    target_start = max(0.0, peak - 12)
    starts = [s["s"] for s in segs if target_start - 8 <= s["s"] <= peak - 1]
    start = min(starts, key=lambda t: abs(t - target_start)) if starts else target_start
    if not starts:  # snap to the nearest word start instead
        ws = [w["s"] for w in words if abs(w["s"] - target_start) <= 3]
        if ws:
            start = min(ws, key=lambda t: abs(t - target_start))

    ideal_end = start + 35
    ends = [s["e"] for s in segs if start + lo <= s["e"] <= start + hi and s["e"] > peak + 2]
    if ends:
        end = min(ends, key=lambda t: abs(t - ideal_end))
    else:
        ws = [w["e"] for w in words if start + lo <= w["e"] <= start + hi]
        end = min(ws, key=lambda t: abs(t - ideal_end)) if ws else min(start + 35, duration)
    return round(start, 2), round(min(end + 0.4, duration), 2)


def make_hook(segs, peak):
    seg = next((s for s in segs if s["s"] <= peak <= s["e"] + 1), None)
    if seg is None and segs:
        seg = min(segs, key=lambda s: abs(s["s"] - peak))
    text = re.sub(r"\s+", " ", (seg or {}).get("text", "")).strip(" .,")
    words = text.split()[:6]
    return " ".join(words).upper() if words else "WAIT FOR IT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--count", type=int, default=0, help="number of clips (default: based on length)")
    ap.add_argument("--min", type=float, default=20)
    ap.add_argument("--max", type=float, default=50)
    a = ap.parse_args()

    tr = json.load(open(os.path.join(a.workdir, "transcript.json"), encoding="utf-8"))
    hype = json.load(open(os.path.join(a.workdir, "hype.json"), encoding="utf-8"))
    segs, words = tr["segments"], tr["words"]
    duration = float(tr.get("duration") or (segs[-1]["e"] if segs else 0))
    count = a.count or max(3, min(12, int(duration // 600) + 2))

    def sec(ts):
        h, m, s = (int(x) for x in ts.split(":"))
        return h * 3600 + m * 60 + s

    clips = []
    for c in hype["candidates"]:
        if len(clips) >= count:
            break
        peak = float(sec(c["peak_ts"]))
        s, e = pick_bounds(segs, words, peak, a.min, a.max, duration)
        if e - s < 10:
            continue
        if any(s < x["end"] and e > x["start"] for x in clips):
            continue
        hook = make_hook(segs, peak)
        clips.append({"id": len(clips) + 1, "start": s, "end": e, "hook": hook,
                      "title": hook.capitalize()[:60] + " #shorts",
                      "reason": f"auto: hype rank {c['rank']} (score {c['score']})",
                      "score": c["score"]})

    clips.sort(key=lambda x: x["start"])
    for i, c in enumerate(clips, 1):
        c["id"] = i
    json.dump(clips, open(os.path.join(a.workdir, "clips.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    for c in clips:
        print(f"#{c['id']:>2}  {c['start']:>8.1f}s → {c['end']:>8.1f}s  ({c['end'] - c['start']:.0f}s)  {c['hook']}")
    print(f"✓ {len(clips)} clips → clips.json")


if __name__ == "__main__":
    main()
