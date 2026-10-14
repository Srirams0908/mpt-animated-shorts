# mpt-animated-shorts

Fully **procedural animated short videos** (vertical 9:16) built on top of
[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT).
No stock footage, no photos, no AI-generated images: every frame is drawn by code
(NumPy + OpenCV), then MoneyPrinterTurbo adds the voiceover, word-by-word captions and music.

This repo does **not** modify MoneyPrinterTurbo. It clones it at run time and drives its CLI.

## What's in here

| Path | What it is |
|---|---|
| `scripts/procedural.py` | The procedural animation: sky, mountains, lake with ripple reflections, forest, a breathing meditator, a flapping butterfly, fireflies, a thought-storm that calms, a breathing ring. Voice-reactive glow. |
| `scripts/run.sh` | End to end: narration -> animation -> captions + music. No API keys needed. |
| `scripts/animate.py`, `scripts/make_shots.sh` | Earlier "route A-lite" experiments that animate *your own still images* with depth parallax and pans. Bring your own images (`s1.png`, `s2.png`, `s3.png`). |
| `docs/ANALYSIS.md` | Reverse-engineering notes on how MoneyPrinterTurbo works, and an assessment of it. |

## Run it

Requirements: `git`, `ffmpeg`, Python 3.11-3.13. Tested on macOS with Python 3.12.

```bash
./scripts/run.sh
```

It clones MoneyPrinterTurbo into `./MoneyPrinterTurbo`, creates a venv, installs dependencies,
generates the narration with Edge TTS (free, no key), renders the animation, and produces the final
MP4 under `MoneyPrinterTurbo/storage/tasks/<task-id>/final-1.mp4`.

The animation step takes about 5 minutes on an Apple-silicon Mac (it renders every frame in Python),
and the final pass about 2 more.

## Honest limitations

- **The scenes are hand-written for one script** (a 22-second meditation piece). `procedural.py`
  hard-codes the scene timings (`DUR`) to the narration beats. A different script needs new scenes
  or new timings. Turning this into "any topic in, video out" would need a planner that picks
  scenes and timings from the script.
- **Style is flat/stylised** (silhouette figure, gradients, glow), not painterly or photoreal.
- The glow pulse follows the audio of one TTS run; re-synthesising the narration can shift it by a few hundredths of a second.
- **Slow to render**, because everything is composited per frame in Python.
- Verified by inspecting rendered frames and measuring the audio mix; there is no automated test suite.
- Background music comes from MoneyPrinterTurbo's bundled library. Check its licence before publishing videos that use it, or run with `--bgm-type none`.

## Credits

[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) by harry0703 (MIT) provides the TTS,
subtitle, mixing and render pipeline.

## License

MIT, see `LICENSE`.
