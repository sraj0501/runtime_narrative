# YouTube creator guide for runtime-narrative

This is a screen-and-voice series. You do not need a camera, lighting kit, paid editor, or a live production setup. Record one short section at a time, read from the episode notes, and join the clips afterward. Keep the existing [16–18 minute flagship script](youtube_flagship_script.md) as a shorter overview; use [the long-form series plan](youtube_series_plan.md) for detailed teaching.

## Free tool stack

| Job | Tool | First action |
|---|---|---|
| Record screen and microphone | [OBS Studio](https://obsproject.com/) | Install from the official site, then run its [Auto-Configuration Wizard](https://obsproject.com/kb/quick-start-guide) for recording. |
| Cut mistakes, add chapter cards, export | [Kdenlive](https://kdenlive.org/) | Install from the official site. Its [quick start](https://docs.kdenlive.org/en/getting_started/quickstart.html) shows import, timeline editing, and export. |
| Upload, captions, chapters | [YouTube Studio](https://studio.youtube.com/) | Upload the finished file as **Unlisted** first and review it before choosing Public. See [YouTube's upload guide](https://support.google.com/youtube/answer/57407?hl=en). |

Use a headset microphone or a laptop microphone for the first rehearsal. A quiet room and a clear speaking distance matter more than buying equipment. OBS and Kdenlive are free and open source; you can keep the full workflow local until upload.

## One-time setup

1. In YouTube Studio, check **Settings → Channel → Feature eligibility**. [YouTube requires account verification for uploads longer than 15 minutes](https://support.google.com/youtube/answer/171664?hl=en). Verification also enables custom thumbnails. Complete that before spending time on a long recording.
2. Install OBS and Kdenlive from the links above. Create a recordings folder **outside this Git repository** so large videos and accidental screen captures cannot be committed.
3. Open the repo in your editor and terminal. Make the terminal/editor font large enough to read at normal laptop size (start around 18–22 px and adjust by looking at a test clip). Use one high-contrast theme. Close unrelated tabs; turn off notifications and message previews.
4. From the repo root, prepare the demo environment **before** recording: `uv sync --group dev --extra console`. The first episode uses only included example files and does not need an LLM account or model.
5. In OBS, make one scene with a display or window capture and a microphone source. Use the Auto-Configuration Wizard, then start with a 16:9 1080p canvas at 30 fps if your computer records smoothly. This is a practical starting point for readable code; [YouTube accepts 30 fps and recommends uploading at the recorded frame rate](https://support.google.com/youtube/answer/1722171?hl=en).
6. Record a 60-second test: speak, scroll through code, run one command, stop, and **watch the file with sound**. Check that text is legible, the mic is louder than notification/system audio, and the cursor is visible. Fix those before recording the episode.

## Recording and editing routine

Record each chapter as a separate clip. Say the chapter title, show the relevant file, explain one idea, run the demo, then stop. If you make a mistake, pause for two seconds and repeat the sentence; edit out the first take. Do not restart a 30-minute recording over one line.

For the simplest robust file workflow, [OBS recommends MKV recording and provides **File → Remux Recordings** to make an MP4](https://obsproject.com/kb/standard-recording-output-guide). Import the MP4 clips into Kdenlive. Cut dead time and mistakes, add a plain title card for each chapter, and export with its [MP4-H264/AAC preset](https://docs.kdenlive.org/en/exporting.html). Keep the recorded frame rate. A clean terminal and a clear voice are enough; skip animations and background music for the first video.

Upload the export as Unlisted. Watch it on a phone or small laptop window, confirm code remains readable, review the automatic captions, and check every link in the description. Add timestamps **after the final edit**, since cuts change timing. [YouTube chapters](https://support.google.com/youtube/answer/9884579?hl=en) need `00:00` first, at least three timestamps in order, and chapters at least 10 seconds long. When the video is ready, choose Public in YouTube Studio.

## What to keep off screen

Use only the synthetic `examples/` data. Hide terminals showing environment variables, API keys, account details, private repositories, customer data, or notifications. Rich diagnostics redact selected **local-variable names**, but exception messages and captured `logging` extra fields may still contain text you supplied. Review the recording before upload; never assume redaction covers every output channel. For the LLM episode, use a local test model or clearly state when a cloud analyzer sends failure context to a provider.

## Repeatable checklist for each episode

- Rehearse every command from the repo root and note the expected result, including intentional failures.
- Record chapter clips; keep the first 10 seconds focused on the concrete problem or output.
- Edit only mistakes, long waits, and unreadable screen moves. Leave enough pause to inspect output.
- Export MP4, watch it once, then upload Unlisted and review captions, chapters, title, thumbnail, and links.
- Publish when the video matches the current released API. Put the package version or commit in the description so future viewers know what they are watching.
