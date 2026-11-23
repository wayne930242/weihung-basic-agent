import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import registerTtsr, { TtsrManager, interrupts } from "../pi/extensions/ttsr.ts";
import { audit, loadStreamRules, readLessons } from "../scripts/lesson-audit.mjs";

// STREAM_RULES_DIR proves another repository's `.pi/rules` with the same harness.
const rules = loadStreamRules(process.env.STREAM_RULES_DIR);

test("the repository ships stream rules", () => {
  assert.ok(rules.length > 0);
});

for (const { name, rule, warnings, blocks, allows } of rules) {
  test(`${name} loads in TTSR and proves itself on its fixtures`, () => {
    assert.deepEqual(warnings, [], "TTSR warnings");
    assert.ok(rule, "TTSR built no rule");
    assert.ok(blocks.length > 0, "needs a `blocks` fixture: the recorded mistake the rule must stop");
    assert.ok(allows.length > 0, "needs an `allows` fixture: a safe neighbor the rule must let through");
    const manager = new TtsrManager([rule]);
    const blocksBash = (command) => manager.check(command, { source: "tool", toolName: "bash", filePaths: [] })
      .some((matched) => interrupts(matched, "tool"));
    for (const command of blocks) assert.ok(blocksBash(command), `should block: ${command}`);
    for (const command of allows) assert.ok(!blocksBash(command), `should allow: ${command}`);
  });
}

const ownRules = { skip: Boolean(process.env.STREAM_RULES_DIR) && "uses this repository's rules" };

test("the basic extension discovers user rules and blocks each recorded bash mistake on repeated calls", ownRules, (t) => {
  const home = mkdtempSync(join(tmpdir(), "basic-ttsr-"));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  symlinkSync(fileURLToPath(new URL("../rules", import.meta.url)), join(home, "rules"));
  const handlers = new Map();
  registerTtsr({
    on: (name, handler) => handlers.set(name, handler),
    appendEntry: () => {},
    registerCommand: () => {},
  });
  const ctx = { cwd: home, ui: { notify: () => {} }, sessionManager: { getBranch: () => [] } };
  const previous = process.env.PI_CODING_AGENT_DIR;
  try {
    process.env.PI_CODING_AGENT_DIR = home;
    handlers.get("session_start")({}, ctx);
  } finally {
    if (previous === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = previous;
  }
  const toolCall = handlers.get("tool_call");
  for (const { name, blocks } of rules) {
    for (const command of blocks) {
      for (const toolCallId of ["first", "repeat"]) {
        const result = toolCall({ toolName: "bash", input: { command }, toolCallId }, ctx);
        assert.equal(result?.block, true, command);
        assert.ok(result.reason.includes(`<rule name="${name}" blocking>`), command);
      }
    }
  }
  assert.equal(toolCall({ toolName: "bash", input: { command: "git status" }, toolCallId: "safe" }, ctx), undefined);
});

test("the audit counts only `lesson` keys as enforcement and lists bare mentions separately", ownRules, (t) => {
  const memory = mkdtempSync(join(tmpdir(), "lesson-audit-"));
  t.after(() => rmSync(memory, { recursive: true, force: true }));
  mkdirSync(join(memory, "daily"));
  writeFileSync(join(memory, "MEMORY.md"), [
    "# Long-term memory",
    "- [failure] Piping a test through `| tail -1` inside an && chain hid a red suite",
    "- [failure] a pre-commit hook ran `git stash` on the shared stack",
    "- [insight] git stash is shared by every worktree",
    "- [correction] read the user's decision verbatim before relaying it",
  ].join("\n"));
  writeFileSync(join(memory, "daily", "2026-10-18.md"), "- 01:02 [failure] used git stash again\n- 01:03 plain log line\n");
  const lessons = readLessons(memory);
  assert.equal(lessons.length, 4);
  const { covered, mentions, prose } = audit(rules, lessons);
  assert.equal(covered.get("no-pipe-tail-in-chain").length, 1, "paired through its lesson key");
  assert.equal(covered.get("no-git-stash").length, 0, "quoting a command is not enforcement");
  assert.equal(mentions.get("no-git-stash").length, 1, "only the quoted command sits at a command position");
  assert.equal(prose.length, 3);
});
