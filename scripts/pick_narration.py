#!/usr/bin/env python3
"""
pick_narration.py — turns a model pick into a short caveman voiceover, and
(optionally) renders it to audio for the TikTok / recap-video pipeline.

Why: the content lane (skills/content/tiktok_playbook.md, SocialSyndicatorAgent,
the MoneyPrinterTurbo recap videos) needs narration. This is the integration
point the `voicebox` repo maps to: pick -> spoken word. It is deliberately
engine-agnostic — the SCRIPT is the durable output; the audio renderer is a
swappable backend.

  * default backend: macOS `say` (always available on this box, zero setup).
  * production backend: Voicebox / Chatterbox / Kokoro (local, watermark-free
    clone of the caveman voice). Swap by pointing --engine at a command that
    reads text on stdin and writes the given output file.

Hard rule (matches every other script here): it NEVER invents a number. It only
speaks the odds / probability / edge that were handed to it. Missing field ->
that line is dropped, not faked.

Input (stdin or --file), either shape:
  a single pick:   {"match": "...", "selection": "...", "decimal": 2.1,
                    "prob": 0.58, "why": "..."}
  a ticket/list:   [ {pick}, {pick}, ... ]   (e.g. bank_builder output legs)

CLI:
  echo '{"match":"Spain v Argentina","selection":"Over 2.5","decimal":1.95,"prob":0.61}' \
      | python3 scripts/pick_narration.py
  ... | python3 scripts/pick_narration.py --json
  ... | python3 scripts/pick_narration.py --audio out.aiff        # macOS say
  ... | python3 scripts/pick_narration.py --audio out.wav --engine "piper -m cave.onnx -f {out}"
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _pct(prob: float | None) -> str | None:
    if prob is None:
        return None
    p = prob * 100 if prob <= 1 else prob  # accept 0-1 or already-percent
    return f"{p:.0f}"


def narrate_one(pick: dict) -> list[str]:
    """One pick -> caveman VO lines. Only speaks fields actually present."""
    match = str(pick.get("match") or pick.get("game") or "").strip()
    selection = str(pick.get("selection") or pick.get("pick") or "").strip()
    decimal = pick.get("decimal") or pick.get("odds") or pick.get("price")
    pct = _pct(pick.get("prob"))
    why = str(pick.get("why") or pick.get("reason") or "").strip()

    lines: list[str] = []
    if match:
        lines.append(f"{match}.")
    if selection:
        lines.append(f"Caveman take {selection}.")
    if decimal:
        lines.append(f"Price {decimal}.")
    if pct:
        lines.append(f"We win {pct} times in hundred.")
    if why:
        lines.append(why if why.endswith(".") else why + ".")
    lines.append("Rock solid. Caveman lock.")
    return lines


def build_script(payload) -> str:
    picks = payload if isinstance(payload, list) else [payload]
    picks = [p for p in picks if isinstance(p, dict)]
    if not picks:
        raise ValueError("no picks in input")

    blocks: list[str] = ["Ugh. Caveman have picks."] if len(picks) > 1 else []
    for i, p in enumerate(picks, 1):
        if len(picks) > 1:
            blocks.append(f"Lock number {i}.")
        blocks.extend(narrate_one(p))
    if len(picks) > 1:
        blocks.append("That the slate. Go get bag.")
    return " ".join(blocks)


def render_audio(text: str, out: str, engine: str | None) -> None:
    """Render text -> audio file. macOS `say` by default; else a custom engine
    command template with {out} placeholder that reads text on stdin."""
    out_path = Path(out)
    if engine:
        cmd = engine.format(out=str(out_path))
        subprocess.run(cmd, shell=True, input=text.encode(), check=True)
        return
    if not shutil.which("say"):
        raise RuntimeError(
            "no --engine given and macOS `say` not found. Pass "
            "--engine 'your-tts -f {out}' (reads text on stdin)."
        )
    # `say` writes AIFF; use a temp text file to preserve punctuation pacing.
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(text)
        tf_path = tf.name
    try:
        subprocess.run(
            ["say", "-v", "Lee", "-r", "165", "-o", str(out_path), "-f", tf_path],
            check=True,
        )
    except subprocess.CalledProcessError:
        # voice "Lee" may be absent; fall back to system default voice.
        subprocess.run(["say", "-r", "165", "-o", str(out_path), "-f", tf_path], check=True)
    finally:
        Path(tf_path).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Caveman voiceover for a pick / ticket.")
    ap.add_argument("--file", help="read pick JSON from file instead of stdin")
    ap.add_argument("--json", action="store_true", help="emit {script} as JSON")
    ap.add_argument("--audio", metavar="OUT", help="also render audio to this path")
    ap.add_argument(
        "--engine",
        help="TTS command template with {out}; reads text on stdin. "
        "Omit to use macOS `say`.",
    )
    args = ap.parse_args()

    raw = Path(args.file).read_text() if args.file else sys.stdin.read()
    try:
        payload = json.loads(raw)
        script = build_script(payload)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"pick_narration: bad input: {e}", file=sys.stderr)
        return 1

    if args.audio:
        try:
            render_audio(script, args.audio, args.engine)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            print(f"pick_narration: audio render failed: {e}", file=sys.stderr)
            return 2

    if args.json:
        out = {"script": script}
        if args.audio:
            out["audio"] = args.audio
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
