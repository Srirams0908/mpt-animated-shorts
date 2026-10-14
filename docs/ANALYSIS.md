# MoneyPrinterTurbo: reverse-engineering notes

Based on reading the source of https://github.com/harry0703/MoneyPrinterTurbo (v1.3.8, October 2026)
and running its CLI. File paths refer to that repo. Not run: the LLM script stage and stock-footage search.

## Architecture

Three front ends (REST API `app/controllers/v1/video.py`, Streamlit `webui/Main.py`, CLI `cli.py`)
all call one function, `_run_pipeline()` in `app/services/task.py`.

```
topic -> [1] LLM script -> [2] LLM search terms -> [3] TTS + word timings
                                                         |
 [7] MP4 <- [6] render <- [5] stock-clip download <- [4] subtitles
```

| # | Stage | Notes |
|---|---|---|
| 1 | Script | One fixed system prompt (`llm.DEFAULT_SCRIPT_SYSTEM_PROMPT`); regex cleanup of markdown and brackets; retries. Skipped if a script is supplied. |
| 2 | Search terms | Second LLM call returning a JSON array of 1-3 word English keywords. No per-scene planning. |
| 3 | Voice | `voice.tts` dispatches by voice name to Edge/Azure/Gemini/ElevenLabs/SiliconFlow/Kokoro/Fish... Returns word-boundary timings. Real duration measured from the file because TTS timing under-counts the tail. |
| 4 | Subtitles | Default: built from TTS timings (free, exact). Optional: faster-whisper + Levenshtein correction against the script. |
| 5 | Footage | Pexels/Pixabay/Coverr per keyword, filtered by aspect/resolution, shuffled, downloaded until the narration is covered. Paid AI-video sources generate per clip on demand. `local` source accepts your own clips/images. |
| 6 | Render | `video.combine_videos` cuts subclips, applies speed/fit/transitions in a thread pool, ffmpeg-concats; `video.generate_video` overlays subtitle `TextClip`s, mixes voice + BGM (fade-out 3 s), writes the MP4 with codec fallback. |

Supporting pieces: in-memory or Redis task queue with concurrency cap and bounded queue
(`app/controllers/manager/`), task state with `failed_stage` (`app/services/state.py`),
~20 LLM providers behind one dispatcher, path-traversal and secret-redaction hardening.

## Assessment

Strengths: mature (about 131k stars, 1,150 commits, ~200 test files / ~46k test lines, CI on Python 3.11 and 3.13 with Redis),
hardened against production edge cases, cheap to run (Edge TTS + Pexels + a cheap LLM), exact subtitle sync from TTS timings.

Weaknesses:

1. **Footage relevance is keyword luck.** Nothing checks a clip matches the sentence being spoken.
2. **No scene model.** The script is one blob; clips are poured onto a timeline until it is long enough.
3. **No quality loop.** No critic on script, hook, or the final video.
4. **Generic output.** Stock footage + TTS is a saturated format.
5. **Slow rendering.** Each clip is encoded by MoviePy, concatenated, then re-encoded with per-subtitle `TextClip` compositing.
6. **Maintainability.** `voice.py` ~3.8k lines, `material.py` ~3k, `llm.py` ~1.4k; many sponsor-driven providers; mostly Chinese comments; `if source == ...` chains rather than a plugin interface.
7. **Operational defaults.** API unauthenticated and bound to `0.0.0.0` until `api_key` is set; tasks are threads in the web process.

## Recommended approach

Reuse the deterministic backbone (queue/state, TTS layer, TTS-timed subtitles, mixing, render fallbacks).
Add agents only for judgment steps it lacks: a scene planner, a script critic, a per-scene footage/visual matcher
(embedding or vision ranking), and a QA pass that watches the draft and re-runs failing scenes.
This repo demonstrates the "visual per beat" idea with hand-written procedural scenes.
