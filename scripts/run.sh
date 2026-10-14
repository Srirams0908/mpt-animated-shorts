#!/usr/bin/env bash
# End-to-end: narration (Edge TTS) -> procedural animation -> captions + music.
# Needs: git, ffmpeg, python3.12 (3.11-3.13 should work). No API keys.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/.."
MPT="$ROOT/MoneyPrinterTurbo"
OUT="$ROOT/out"; mkdir -p "$OUT"
PY="${PYTHON:-python3.12}"
# BGM_TYPE=none for a music-free render (default: random track from MoneyPrinterTurbo's library)
BGM_TYPE="${BGM_TYPE:-random}"

if [ ! -d "$MPT" ]; then
  git clone --depth 1 https://github.com/harry0703/MoneyPrinterTurbo "$MPT"
fi
cd "$MPT"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
  . .venv/bin/activate
  pip install -q -r requirements.txt opencv-python-headless
else
  . .venv/bin/activate
fi
[ -f config.toml ] || cp config.example.toml config.toml

SCRIPT="Most people think meditation means emptying your mind. It doesn't. It means noticing where your attention goes, and gently bringing it back. Do that for just ten minutes a day, and studies link it with lower stress, better focus, and deeper sleep. Start small. One breath at a time."
VOICE="en-US-AriaNeural-Female"

# 1) narration only (used to drive the voice-reactive glow)
AUDIO=$(python cli.py --video-subject "meditation" --video-script "$SCRIPT" --video-source local \
  --voice-name "$VOICE" --video-language en-US --stop-at audio 2>/dev/null \
  | tail -1 | python -c "import sys,json; print(json.loads(sys.stdin.read())['result']['audio_file'])")
echo "audio: $AUDIO"

# 2) procedural animation (no photos, no AI images)
python "$HERE/procedural.py" "$OUT/animation.mp4" "$AUDIO"

# 3) narration + word-by-word captions + music, using MoneyPrinterTurbo's own renderer
python cli.py --video-subject "meditation" --video-script "$SCRIPT" --video-terms meditation \
  --video-source local --video-materials "$OUT/animation.mp4" \
  --video-concat-mode sequential --video-clip-duration 30 \
  --voice-name "$VOICE" --video-language en-US \
  --bgm-type "$BGM_TYPE" --bgm-volume 0.14 --video-aspect 9:16 \
  --font-name BeVietnamPro-Bold.ttf --font-size 84 --stroke-width 5 --stroke-color "#101828" \
  --text-fore-color "#FFE9A8" --subtitle-position custom --custom-position 80 \
  --subtitle-display-mode word_by_word --subtitle-animation pop_spring
echo "Final video is under $MPT/storage/tasks/<task-id>/final-1.mp4"
