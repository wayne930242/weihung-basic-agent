---
name: agent-desktop
description: Use when operating a native desktop app (macOS, Windows, or Linux) through its accessibility tree, such as clicking, typing, reading a window, a menu, the menu bar, the Dock, or a system dialog, or checking a desktop UI. Web pages go to the browser tools (rules/browser.md).
---

# agent-desktop

The `agent-desktop` CLI reads a desktop app's accessibility tree (AX on macOS, UI Automation on Windows, AT-SPI on Linux) as JSON with a ref for every element, and acts on those refs. The installer puts it on the PATH with `npm install -g`.

This file only points at the guides. Before the first command in a session, load the ones that match the installed version:

```bash
agent-desktop skills get desktop      # the observe, act, verify loop, refs, and retry rules
agent-desktop skills get platform     # what differs on this OS: permissions, surfaces, headed actions
agent-desktop <command> --help        # flags for one command
```

Rules this setup adds:

- Stay headless. Ref actions never move the pointer or take focus, so the user keeps the machine. Pass `--headed` only when the user asked for physical input or a guide says the action needs it (`double-click`, `hover`, `drag`), and say so first.
- Retry a failed command only when its `error.disposition.retry` is `safe`; otherwise snapshot again and decide.
- Judge every action by a new snapshot, `get`, or `is`, never by its return code.
- When `agent-desktop permissions` reports a denied permission, run `agent-desktop permissions --guide` only with the user at the machine, since the grant takes their Touch ID or password; tell them which permission is missing.
- Close what you launched with `close-app` when the work ends.
