# Episode 1 video package

The finished, locally rendered video is at [`video_outputs/episode_01/runtime_narrative_episode_01.mp4`](video_outputs/episode_01/runtime_narrative_episode_01.mp4). It is **10:31**, 1280 × 720 at 30 fps, H.264 video with AAC audio. The project also exports [`runtime_narrative_episode_01.srt`](video_outputs/episode_01/runtime_narrative_episode_01.srt) for YouTube captions and [`thumbnail.png`](video_outputs/episode_01/thumbnail.png). Exports are ignored by Git because they are generated media.

The narration uses FFmpeg's offline Flite voice. It is a complete first cut, but it sounds synthetic. A higher-quality voiceover can be substituted in a video editor; re-time the captions if its pacing changes. The slides, source content, captions, and scene timings are built from [`build_episode_01_video.py`](build_episode_01_video.py). Blender is not required for this code-and-diagram format.

## YouTube upload text

**Title:** Python Errors with Context — Runtime Narrative Tutorial (Stories, Stages, Failures)

**Description:**

Learn Runtime Narrative with a full customer-import walkthrough. We compare a raw Python traceback with a named execution story, then use `story()` and `stage()`, read a successful run, diagnose a deliberate failure, and follow a nested async database call. The core examples run locally without an AI account.

Documentation: https://runtime-narrative.netlify.app/  
Source and examples: https://github.com/sraj0501/runtime_narrative  
Package: https://pypi.org/project/runtime-narrative/

00:00 The traceback problem  
01:54 Story and stage basics  
03:43 Reading a successful run  
05:06 Diagnosing a failure  
07:08 Nested stories  
08:33 Lean and rich diagnostics  
09:30 Try it yourself

The code examples are from runtime-narrative 1.5.4. All demo data is synthetic. Captions are available.

## Rebuild

On Windows, with FFmpeg on `PATH` and Pillow available to Python:

```powershell
python marketing/build_episode_01_video.py
```

The script renders original slide artwork, an offline narration WAV for every caption, individual motion clips, the final MP4, captions, chapters, and thumbnail. If you edit the words or visuals, rebuild all outputs so their timing stays aligned.
