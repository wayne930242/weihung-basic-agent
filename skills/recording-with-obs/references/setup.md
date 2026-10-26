# One-time OBS setup

Done on this Mac on 2026-10-20 with OBS 32.2.2. Repeat only on a new machine or after OBS's settings are reset.

1. Install: `brew install --cask obs`.
2. With OBS closed, enable the websocket with a generated password. The password lives only in `~/.config/obs-websocket/password` (mode 600), where `obs.mjs` reads it:

   ```bash
   umask 077
   mkdir -p ~/.config/obs-websocket "$HOME/Library/Application Support/obs-studio/plugin_config/obs-websocket"
   [ -s ~/.config/obs-websocket/password ] || openssl rand -hex 16 | tr -d '\n' > ~/.config/obs-websocket/password
   PW="$(cat ~/.config/obs-websocket/password)" python3 -I -c '
   import json, os, sys
   json.dump({"alerts_enabled": False, "auth_required": True, "first_load": False, "server_enabled": True,
              "server_password": os.environ["PW"], "server_port": 4455}, open(sys.argv[1], "w"), indent=2)
   ' "$HOME/Library/Application Support/obs-studio/plugin_config/obs-websocket/config.json"
   ```

   obs-websocket listens on every interface, so keep authentication on.
3. Open OBS. On first launch it shows a permissions dialog: the user grants Screen Recording (required; system sound comes with it) and Microphone, then restarts OBS so Screen Recording takes effect. The user cancels the auto-configuration wizard.
4. Recording settings, through `obs.mjs raw`, then restart OBS:

   ```json
   [["SetProfileParameter", {"parameterCategory": "SimpleOutput", "parameterName": "RecFormat2", "parameterValue": "hybrid_mp4"}],
    ["SetProfileParameter", {"parameterCategory": "SimpleOutput", "parameterName": "RecEncoder", "parameterValue": "apple_h264"}],
    ["SetProfileParameter", {"parameterCategory": "SimpleOutput", "parameterName": "RecQuality", "parameterValue": "Small"}],
    ["SetVideoSettings", {"baseWidth": 1920, "baseHeight": 1080, "outputWidth": 1920, "outputHeight": 1080, "fpsNumerator": 30, "fpsDenominator": 1}]]
   ```

5. Scenes: `obs.mjs target front` creates `瀏覽器視窗` with its source. For `整個螢幕`, rename the default `Scene` and add the display source with the main display's uuid, which this prints:

   ```bash
   printf 'import CoreGraphics\nimport ColorSync\nprint(CFUUIDCreateString(nil, CGDisplayCreateUUIDFromDisplayID(CGMainDisplayID())!.takeRetainedValue())!)\n' > /tmp/main-display.swift
   swift /tmp/main-display.swift
   ```

   ```json
   [["SetSceneName", {"sceneName": "Scene", "newSceneName": "整個螢幕"}],
    ["CreateInput", {"sceneName": "整個螢幕", "inputName": "螢幕", "inputKind": "screen_capture",
                     "inputSettings": {"type": 0, "display_uuid": "<uuid>", "show_cursor": true}}],
    ["SetSceneItemTransform", {"sceneName": "整個螢幕", "sceneItemId": 1, "sceneItemTransform":
      {"boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsWidth": 1920, "boundsHeight": 1080, "boundsAlignment": 0, "alignment": 5, "positionX": 0, "positionY": 0}}]]
   ```

6. Give the terminal running pi (Ghostty) the Accessibility permission, which `webarea.swift` needs to find the page area.
7. Workspace G comes from the AeroSpace rule in `~/dotfiles-macos` (`bin/aerospace-chrome-extra`, commit d82ff11): the oldest Chrome window stays in C and every later one moves to G. Without it, `open` still works and the window stays where Chrome puts it.
8. Check: `obs.mjs open https://www.youtube.com/watch?v=dQw4w9WgXcQ`, `start`, wait a few seconds, `stop`, then `check` the file.
