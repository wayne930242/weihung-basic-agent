#!/usr/bin/env node
// Controls OBS Studio through its built-in obs-websocket v5 server.
// Usage: node obs.mjs <command> [args]; run without arguments for the command list.
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OBS_URL = "ws://127.0.0.1:4455";
const PASSWORD_FILE = join(homedir(), ".config/obs-websocket/password");
const BROWSER_SCENE = "瀏覽器視窗";
const BROWSER_SOURCE = "Chrome 視窗";
const SCREEN_SCENE = "整個螢幕";
const MIC = "Mic/Aux";
const FIT = {
  boundsType: "OBS_BOUNDS_SCALE_INNER", boundsWidth: 1920, boundsHeight: 1080,
  boundsAlignment: 0, alignment: 5, positionX: 0, positionY: 0,
};

const USAGE = `commands:
  launch                 open OBS and wait for its websocket
  status                 scene, recording state, mic, target window
  windows [app]          list on-screen windows of app (default "Google Chrome")
  open <url> [WxH]       open url in a new Chrome window whose page area is WxH points
                         (default 1280x720), record it and crop to the page
  target <id|front>      record that Chrome window (scene "${BROWSER_SCENE}")
  crop page|off          crop the recorded Chrome window to its page area, or undo
  screen                 record the whole main display (scene "${SCREEN_SCENE}")
  mic on|off             unmute or mute the microphone
  start                  start recording
  stop                   stop recording and print the file path
  preview <out.jpg>      save a screenshot of what is being recorded
  check <file>           print streams, duration and audio peak of a recording
  raw '<json>'           send [["RequestType", {data}], ...] and print responses`;

const sha = (s) => createHash("sha256").update(s).digest("base64");

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(OBS_URL);
    const pending = new Map();
    let id = 0;
    const call = (requestType, requestData = {}) => new Promise((res, rej) => {
      const requestId = String(++id);
      pending.set(requestId, { res, rej, requestType });
      ws.send(JSON.stringify({ op: 6, d: { requestType, requestId, requestData } }));
    });
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.op === 0) {
        const d = { rpcVersion: 1, eventSubscriptions: 0 };
        if (msg.d.authentication) {
          const password = readFileSync(PASSWORD_FILE, "utf8").trim();
          const { salt, challenge } = msg.d.authentication;
          d.authentication = sha(sha(password + salt) + challenge);
        }
        ws.send(JSON.stringify({ op: 1, d }));
      } else if (msg.op === 2) {
        resolve({ call, close: () => ws.close() });
      } else if (msg.op === 7) {
        const p = pending.get(msg.d.requestId);
        pending.delete(msg.d.requestId);
        const { result, code, comment } = msg.d.requestStatus;
        if (result) p.res(msg.d.responseData ?? {});
        else p.rej(new Error(`${p.requestType} failed (${code}): ${comment ?? ""}`));
      }
    };
    ws.onerror = () => reject(new Error(`cannot reach OBS at ${OBS_URL}; run "launch" first`));
    ws.onclose = (e) => {
      if (e.code === 4009) reject(new Error(`authentication failed; check ${PASSWORD_FILE}`));
      for (const p of pending.values()) p.rej(new Error(`OBS closed the connection (${e.code}); it may have crashed`));
    };
  });
}

async function withObs(fn) {
  const obs = await connect();
  try { return await fn(obs.call); } finally { obs.close(); }
}

function listWindows(app = "Google Chrome") {
  const out = execFileSync("swift", [join(HERE, "windows.swift"), app], { encoding: "utf8" });
  return out.split("\n").filter(Boolean).map((line) => {
    const [id, size, ...title] = line.split("\t");
    return { id: Number(id), size, title: title.join("\t") };
  });
}

async function ensureScene(call, sceneName) {
  const { scenes } = await call("GetSceneList");
  if (!scenes.some((s) => s.sceneName === sceneName)) await call("CreateScene", { sceneName });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Insets of the page area inside a Chrome window, in points, plus the window size.
function webArea(windowId) {
  const out = execFileSync("swift", [join(HERE, "webarea.swift"), String(windowId)], { encoding: "utf8" });
  const [top, left, bottom, right, width, height] = out.trim().split(" ").map(Number);
  return { top, left, bottom, right, width, height };
}

// Runs an AppleScript with arguments passed as argv, never interpolated into the script.
function osascript(script, ...args) {
  return execFileSync("osascript", ["-e", script, ...args], { encoding: "utf8" }).trim();
}

async function aimAt(call, win) {
  const inputSettings = { type: 1, application: "com.google.Chrome", window: win.id, show_cursor: true };
  await ensureScene(call, BROWSER_SCENE);
  // The capture source only sees windows that existed when it was created, so a window
  // opened later gets no frames until the source is rebuilt.
  if (await sceneItemId(call, BROWSER_SCENE, BROWSER_SOURCE) !== null) {
    await call("RemoveInput", { inputName: BROWSER_SOURCE });
    await sleep(500);
  }
  const { sceneItemId: itemId } = await call("CreateInput", {
    sceneName: BROWSER_SCENE, inputName: BROWSER_SOURCE, inputKind: "screen_capture", inputSettings,
  });
  const sceneItemTransform = { ...FIT, cropTop: 0, cropLeft: 0, cropBottom: 0, cropRight: 0 };
  await call("SetSceneItemTransform", { sceneName: BROWSER_SCENE, sceneItemId: itemId, sceneItemTransform });
  await call("SetCurrentProgramScene", { sceneName: BROWSER_SCENE });
  return itemId;
}

// Crops the browser source to the page area. The crop is in source pixels, so the
// window's points are scaled by the capture's pixel density.
async function cropToPage(call) {
  const itemId = await sceneItemId(call, BROWSER_SCENE, BROWSER_SOURCE);
  if (itemId === null) throw new Error(`no source "${BROWSER_SOURCE}"; run "target" first`);
  const { inputSettings } = await call("GetInputSettings", { inputName: BROWSER_SOURCE });
  const area = webArea(inputSettings.window);
  let sourceWidth = 0;
  for (let i = 0; i < 20 && !sourceWidth; i++) {
    ({ sourceWidth } = (await call("GetSceneItemTransform", { sceneName: BROWSER_SCENE, sceneItemId: itemId })).sceneItemTransform);
    if (!sourceWidth) await sleep(250);
  }
  if (!sourceWidth) throw new Error("OBS has no frame from the window yet; is it minimized?");
  const scale = sourceWidth / area.width;
  const crop = {
    cropTop: Math.round(area.top * scale), cropLeft: Math.round(area.left * scale),
    cropBottom: Math.round(area.bottom * scale), cropRight: Math.round(area.right * scale),
  };
  await call("SetSceneItemTransform", { sceneName: BROWSER_SCENE, sceneItemId: itemId, sceneItemTransform: { ...FIT, ...crop } });
  const pageWidth = area.width - area.left - area.right;
  const pageHeight = area.height - area.top - area.bottom;
  return { pageWidth, pageHeight, crop };
}

async function sceneItemId(call, sceneName, sourceName) {
  try {
    return (await call("GetSceneItemId", { sceneName, sourceName })).sceneItemId;
  } catch {
    return null;
  }
}

const commands = {
  async launch() {
    execFileSync("open", ["-a", "OBS"]);
    for (let i = 0; i < 30; i++) {
      try {
        const v = await withObs((call) => call("GetVersion"));
        console.log(`OBS ${v.obsVersion} ready (obs-websocket ${v.obsWebSocketVersion})`);
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    throw new Error("OBS did not open its websocket within 30 s; check the OBS window for a dialog");
  },

  status: () => withObs(async (call) => {
    const { sceneName } = await call("GetCurrentProgramScene");
    const rec = await call("GetRecordStatus");
    const { inputMuted } = await call("GetInputMute", { inputName: MIC });
    const { recordDirectory } = await call("GetRecordDirectory");
    let target = "(none)";
    try {
      const { inputSettings } = await call("GetInputSettings", { inputName: BROWSER_SOURCE });
      const win = listWindows().find((w) => w.id === inputSettings.window);
      target = `${inputSettings.window} ${win ? `"${win.title}" ${win.size}` : "(window not on screen)"}`;
    } catch {}
    console.log(`scene: ${sceneName}
recording: ${rec.outputActive ? `yes, ${rec.outputTimecode}` : "no"}
mic: ${inputMuted ? "muted" : "on"}
browser target: ${target}
saves to: ${recordDirectory}`);
  }),

  windows(app) {
    const wins = listWindows(app);
    if (!wins.length) console.log(`no on-screen windows of ${app ?? "Google Chrome"}`);
    for (const w of wins) console.log(`${w.id}\t${w.size}\t${w.title}`);
  },

  open: (url, size = "1280x720") => withObs(async (call) => {
    if (!url) throw new Error("usage: open <url> [WxH]");
    const [pageWidth, pageHeight] = size.split("x").map(Number);
    if (!pageWidth || !pageHeight) throw new Error(`size must look like 1280x720, got ${size}`);
    const before = new Set(listWindows().map((w) => w.id));
    // Setting the URL in the same breath as creating the window once lost the window;
    // loading is missing value while navigation starts.
    const chromeId = osascript(`on run argv
      tell application "Google Chrome" to set wid to id of (make new window)
      delay 1
      tell application "Google Chrome"
        set URL of active tab of window id wid to item 1 of argv
        repeat 120 times
          delay 0.25
          try
            if (loading of active tab of window id wid) is false then exit repeat
          end try
        end repeat
        return id of window id wid
      end tell
    end run`, url);
    let win;
    for (let i = 0; i < 20 && !win; i++) {
      win = listWindows().find((w) => !before.has(w.id));
      if (!win) await sleep(250);
    }
    if (!win) throw new Error("the new Chrome window did not appear");
    // AeroSpace tiles new windows and would undo the size set below.
    try { execFileSync("aerospace", ["layout", "floating", "--window-id", String(win.id)], { stdio: "ignore" }); } catch {}
    const area = webArea(win.id);
    const width = pageWidth + area.left + area.right;
    const height = pageHeight + area.top + area.bottom;
    osascript(`on run argv
      tell application "Google Chrome" to set bounds of (window id (item 1 of argv as integer)) to {20, 40, 20 + (item 2 of argv as integer), 40 + (item 3 of argv as integer)}
    end run`, chromeId, String(width), String(height));
    await sleep(500);
    await aimAt(call, win);
    const result = await cropToPage(call);
    console.log(`recording target: ${win.id}, page area ${result.pageWidth}x${result.pageHeight} points`);
    if (result.pageWidth !== pageWidth || result.pageHeight !== pageHeight) {
      console.log(`page area differs from ${size}: the window did not fit on screen; black bars will show`);
    }
  }),

  target: (arg) => withObs(async (call) => {
    if (!arg) throw new Error("usage: target <window id|front>");
    const wins = listWindows();
    const win = arg === "front" ? wins[0] : wins.find((w) => w.id === Number(arg));
    if (!win) throw new Error(`no on-screen Chrome window ${arg}; run "windows"`);
    await aimAt(call, win);
    console.log(`recording target: ${win.id} "${win.title}" ${win.size}`);
  }),

  crop: (mode) => withObs(async (call) => {
    if (mode === "off") {
      const itemId = await sceneItemId(call, BROWSER_SCENE, BROWSER_SOURCE);
      if (itemId === null) throw new Error(`no source "${BROWSER_SOURCE}"`);
      const sceneItemTransform = { ...FIT, cropTop: 0, cropLeft: 0, cropBottom: 0, cropRight: 0 };
      await call("SetSceneItemTransform", { sceneName: BROWSER_SCENE, sceneItemId: itemId, sceneItemTransform });
      console.log("crop: off");
      return;
    }
    if (mode !== "page") throw new Error("usage: crop page|off");
    const { pageWidth, pageHeight, crop } = await cropToPage(call);
    console.log(`crop: page area ${pageWidth}x${pageHeight} points (${JSON.stringify(crop)} px)`);
  }),

  screen: () => withObs(async (call) => {
    await ensureScene(call, SCREEN_SCENE);
    if (await sceneItemId(call, SCREEN_SCENE, "螢幕") === null) {
      throw new Error(`scene "${SCREEN_SCENE}" has no source "螢幕"; create it as references/setup.md describes`);
    }
    await call("SetCurrentProgramScene", { sceneName: SCREEN_SCENE });
    console.log(`scene: ${SCREEN_SCENE}`);
  }),

  mic: (state) => withObs(async (call) => {
    if (state !== "on" && state !== "off") throw new Error("usage: mic on|off");
    await call("SetInputMute", { inputName: MIC, inputMuted: state === "off" });
    console.log(`mic: ${state === "off" ? "muted" : "on"}`);
  }),

  start: () => withObs(async (call) => {
    await call("StartRecord");
    console.log("recording started");
  }),

  stop: () => withObs(async (call) => {
    const { outputPath } = await call("StopRecord");
    console.log(outputPath);
  }),

  preview: (out) => withObs(async (call) => {
    if (!out) throw new Error("usage: preview <out.jpg>");
    const { sceneName } = await call("GetCurrentProgramScene");
    const { imageData } = await call("GetSourceScreenshot", {
      sourceName: sceneName, imageFormat: "jpg", imageWidth: 960, imageHeight: 540, imageCompressionQuality: 70,
    });
    writeFileSync(out, Buffer.from(imageData.split(",", 2)[1], "base64"));
    console.log(out);
  }),

  check(file) {
    if (!file) throw new Error("usage: check <file>");
    console.log(execFileSync("ffprobe", ["-v", "error", "-show_entries",
      "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration", "-of", "compact", file], { encoding: "utf8" }).trim());
    // volumedetect reports on stderr.
    const vol = spawnSync("ffmpeg", ["-hide_banner", "-nostats", "-i", file, "-vn", "-af", "volumedetect", "-f", "null", "-"],
      { encoding: "utf8" }).stderr;
    console.log(vol.split("\n").filter((l) => /mean_volume|max_volume/.test(l)).map((l) => l.replace(/^.*\] /, "")).join("\n"));
  },

  raw: (json) => withObs(async (call) => {
    for (const [type, data] of JSON.parse(json)) console.log(JSON.stringify({ [type]: await call(type, data) }));
  }),
};

const [name, ...args] = process.argv.slice(2);
if (!commands[name]) {
  console.log(USAGE);
  process.exit(name ? 1 : 0);
}
try {
  await commands[name](...args);
} catch (err) {
  console.error(err.message);
  process.exit(1);
}
