---
name: recording-with-obs
description: Use when the user wants to record a web page, a YouTube video or live stream, a browser tab, or the screen with its sound, often by handing over just a link (錄影, 錄製, 錄螢幕, 錄分頁, 錄瀏覽器, 幫我錄這個連結, 開始錄, 停止錄, OBS).
---

# Recording with OBS

OBS Studio on this Mac records a Chrome window cropped to its page area, together with Chrome's sound, and `scripts/obs.mjs` drives it through OBS's built-in websocket. Run every command as `node <skill dir>/scripts/obs.mjs <command>`; `node obs.mjs` alone prints the command list.

The user hands over a link and expects the recording to run without further setup. They log in themselves when a page asks.

## Workflow

1. **Bring OBS up**: run `launch`, then `status`. When `launch` cannot reach the websocket on a machine never set up, follow [references/setup.md](references/setup.md).
2. **Open the link**: run `open <url>`. It opens the link in a new Chrome window, which AeroSpace places in workspace G (the user's dotfiles send every Chrome window after the first there), sizes its page area to 1280x720, points OBS at it, and crops away Chrome's tab strip, toolbar and side tabs. When the page needs a login, tell the user to log in inside that window in workspace G (`alt-g`), then run `crop page` again once the page is back.
3. **Check the frame and the mic**: run `preview /tmp/obs-preview.jpg` and read the image; it must show only the page. The mic is muted unless the user asks for their voice (`mic on`).
4. **Record**: run `start` at once, or schedule it for a named time window (an event, a live stream) with `MonitorCreate` wall-clock waiters (`while [ "$(date +%s)" -lt <epoch> ]; do sleep 20; done`, timeout 0) whose `onDone` runs steps 1–4 a few minutes before the start and step 5 a few minutes after the end. Use these instead of `LoopCreate` cron loops: a loop's timer stops while the Mac sleeps and fires late after it wakes. When the Mac may sleep before the start, have the user run `sudo pmset schedule wake "MM/DD/YYYY HH:MM:SS"` through `robot_hand` (herdr-type), and add a waiter that `exec caffeinate -ims -t <seconds>` from the wake time to the end. Tell the user to keep this pi session open, the lid open and power connected. A pi session recovery drops every monitor and loop, caffeinate included: after one, run `MonitorList` and recreate what the schedule still needs. Recordings take about 0.9 GB per hour; compare the length with `df -h ~` first. The user can keep working in other workspaces: a window in a hidden workspace keeps rendering and its sound keeps recording. A live stream must be playing; read the preview again after starting, and when it shows a paused or waiting player, ask the user to press play in workspace G.
5. **Stop and verify**: `stop` prints the file path (`~/Movies/*.mp4`). Run `check <file>`: a 1920x1080 video stream and a `max_volume` above about -60 dB mean picture and sound were captured; a peak near -91 dB means silence, so confirm the video was playing and unmuted.

**Complete when:** `check` on the recording shows the video stream and an audible audio peak, and the user has the file path.

## Reference

- Window capture records the sound of all of Chrome; other tabs playing sound end up in the recording, so ask the user to mute them.
- `target <id|front>` and `crop page|off` aim at a window the user already has open; `windows` lists Chrome windows with their ids. `screen` records the whole main display instead.
- OBS's capture source only sees windows that existed when it was created, so every `target` and `open` rebuilds the source `Chrome 視窗` in scene `瀏覽器視窗`.
- `scripts/webarea.swift` finds the page area through the Accessibility API; the terminal running pi needs the Accessibility permission. `scripts/windows.swift` lists window ids.
- Never send `GetInputPropertiesListPropertyItems` through `raw`: in OBS 32.2.2 (obs-websocket 5.7.4) it crashed OBS with a null-string segfault. Creating a `screen_capture` input in display mode without a valid `display_uuid` also crashed it; [references/setup.md](references/setup.md) shows how to get the uuid.
- Changes to recording format or encoder take effect after OBS restarts; quit it with `osascript -e 'quit app "OBS"'`, which reports `User canceled` yet quits and saves.
